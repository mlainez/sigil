(* Sigil Tree-Walking Interpreter *)

open Types
open Ast
open Lexer
open Parser
open Unix

(* Diagnostic state — see definitions further down for the canonical comments.
   Forward-declared here because print/println at line ~2640 set output_emitted
   and (argv) at line ~2480 reads diagnose_enabled, both before the bulk of
   interpreter helpers. The vm.ml entry checks output_emitted after
   execute_module returns.

   Diagnostics are ON by default — they help both human users and the
   agent harness's retry loop catch silent misuse (model writes (argv)
   when input is in $0; program runs without producing output). To
   silence (e.g. in batch test runs that assert on stderr), set
   SIGIL_DIAGNOSE=0. *)
let output_emitted = ref false

let diagnose_enabled () =
  match Sys.getenv_opt "SIGIL_DIAGNOSE" with
  | Some "0" | Some "off" | Some "false" -> false
  | _ -> true

(* Runtime values *)
type value =
  | VInt of int64
  | VFloat of float
  | VDecimal of string
  | VString of string
  | VBool of bool
  | VUnit
  | VArray of value array ref
  | VMap of (string, value) Hashtbl.t * string list ref  (* hashtbl + insertion-ordered keys *)
  | VFunction of string * param list * type_kind * expr list
  | VClosure of string list * expr list * (string * value) list
      (* params, body, captured-env snapshot (var name + value pairs) *)
  | VBuiltin of string
      (* Reference to a builtin function by name — used when a builtin is
         passed as a first-class value to a higher-order function. *)
  | VSocket of Unix.file_descr
  | VTlsSocket of Ssl.socket
  | VWsSocket of ws_transport
  | VChannel of Unix.file_descr * Unix.file_descr * int option  (* fd1, fd2, optional pid *)
  | VProcess of int  (* PID *)

and ws_transport =
  | WsPlain of Unix.file_descr
  | WsTls of Ssl.socket

(* Exceptions *)
exception Return of value
exception Break
exception Continue
exception GotoLabel of string
exception RuntimeError of string

(* Check if a value matches a declared type *)
let type_matches (tk : type_kind) (v : value) : bool =
  match tk, v with
  | TInt, VInt _ -> true
  | TFloat, VFloat _ -> true
  | TDecimal, VDecimal _ -> true
  | TString, VString _ -> true
  | TBool, VBool _ -> true
  | TUnit, VUnit -> true
  | TArray _, VArray _ -> true
  | TMap _, VMap _ -> true
  | TJson, _ -> true  (* JSON can hold any value *)
  | TRegex, VString _ -> true  (* regex patterns stored as strings *)
  | TProcess, VProcess _ -> true
  | TProcess, VChannel _ -> true  (* process_spawn returns VChannel *)
  | TSocket, VSocket _ -> true
  | TSocket, VTlsSocket _ -> true
  | TSocket, VWsSocket _ -> true
  | TSocket, VChannel _ -> true
  | TFunction _, VFunction _ -> true
  | TFunction _, VClosure _ -> true
  | TFunction _, VBuiltin _ -> true
  | _ -> false

let string_of_type_kind = function
  | TInt -> "int" | TFloat -> "float" | TDecimal -> "decimal"
  | TString -> "string" | TBool -> "bool" | TUnit -> "unit"
  | TArray _ -> "array" | TMap _ -> "map" | TJson -> "json"
  | TRegex -> "regex" | TProcess -> "process" | TSocket -> "socket"
  | TFunction _ -> "function"

let string_of_value_type = function
  | VInt _ -> "int" | VFloat _ -> "float" | VDecimal _ -> "decimal"
  | VString _ -> "string" | VBool _ -> "bool" | VUnit -> "unit"
  | VArray _ -> "array" | VMap _ -> "map" | VFunction _ -> "function"
  | VClosure _ -> "function" | VBuiltin _ -> "function"
  | VSocket _ -> "socket" | VTlsSocket _ -> "socket" | VWsSocket _ -> "socket"
  | VChannel _ -> "socket" | VProcess _ -> "process"

(* Build a "(t1 t2 t3)" type-tuple string from a list of values. Used inside
   builtin error messages so a model that misuses an op gets the actual shape
   it passed alongside the expected shape — the prior generic
   "Invalid arguments to X" surfaced no signal a retry could correct on. *)
let fmt_arg_types vs =
  "(" ^ String.concat " " (List.map string_of_value_type vs) ^ ")"

(* Environment for variable bindings *)
type env = (string, value) Hashtbl.t

let env_create () = Hashtbl.create 32
let env_set env name value = Hashtbl.replace env name value
let env_get env name =
  try Hashtbl.find env name
  with Not_found -> raise (RuntimeError ("Undefined variable: " ^ name))

(* Ordered map helpers *)
let make_vmap () = VMap (Hashtbl.create 16, ref [])
let vmap_set m keys k v =
  if not (Hashtbl.mem m k) then keys := !keys @ [k];
  Hashtbl.replace m k v
let vmap_delete m keys k =
  Hashtbl.remove m k;
  keys := List.filter (fun x -> x <> k) !keys

(* OCaml's Str library doesn't support brace quantifiers ({n}, {n,}, {n,m}).
   Expand them inline against the preceding atom (single char, escape sequence,
   character class, or capture group):
     X{n}    → XXX...X    (n copies)
     X{n,}   → XX...X X*   (n copies + greedy any-more)
     X{n,m}  → XX...X X?...X?  (n copies + (m-n) optional copies)
   This keeps Str-only regexes valid and handles the common LLM pattern. *)
let regex_translate_braces s =
  let n = String.length s in
  (* Find the start index of the atom ending at index `end_excl` (exclusive),
     scanning backward from the position of the opening `{`. *)
  let find_atom_start end_excl =
    if end_excl <= 0 then None
    else
      let last = end_excl - 1 in
      let c = s.[last] in
      if c = ']' then begin
        let depth = ref 1 in
        let j = ref (last - 1) in
        let found = ref None in
        while !j >= 0 && !found = None do
          let cj = s.[!j] in
          if cj = '\\' && !j > 0 then j := !j - 2
          else if cj = ']' then begin decr depth; decr j end
          else if cj = '[' then begin
            incr depth;
            if !depth = 0 then found := Some !j
            else decr j
          end else decr j
        done;
        if !found = None && !depth = 1 then None else !found
      end
      else if c = ')' then begin
        let depth = ref 1 in
        let j = ref (last - 1) in
        let found = ref None in
        while !j >= 0 && !found = None do
          let cj = s.[!j] in
          if cj = '\\' && !j + 1 < n then begin
            let next = s.[!j + 1] in
            if next = '(' then begin
              decr depth;
              if !depth = 0 then found := Some !j
              else j := !j - 1
            end else if next = ')' then begin
              incr depth;
              j := !j - 1
            end else j := !j - 1
          end else decr j
        done;
        !found
      end
      else if last > 0 && s.[last - 1] = '\\' then Some (last - 1)
      else Some last
  in
  let buf = Buffer.create (n + 8) in
  let i = ref 0 in
  let last_atom_start = ref (-1) in
  let last_atom_end = ref (-1) in
  while !i < n do
    let c = s.[!i] in
    if c = '\\' && !i + 1 < n then begin
      Buffer.add_char buf c;
      Buffer.add_char buf s.[!i + 1];
      last_atom_start := Buffer.length buf - 2;
      last_atom_end := Buffer.length buf;
      i := !i + 2
    end
    else if c = '{' then begin
      let j = ref (!i + 1) in
      let valid = ref true in
      while !j < n && s.[!j] <> '}' && !valid do
        let cc = s.[!j] in
        if (cc >= '0' && cc <= '9') || cc = ',' then incr j
        else valid := false
      done;
      if !valid && !j < n && s.[!j] = '}' && !j > !i + 1
         && !last_atom_start >= 0 then begin
        let spec = String.sub s (!i + 1) (!j - !i - 1) in
        let parts = String.split_on_char ',' spec in
        let lo, hi =
          match parts with
          | [a] when a <> "" -> (int_of_string a, Some (int_of_string a))
          | [a; ""] when a <> "" -> (int_of_string a, None)
          | [a; b] when a <> "" && b <> "" ->
              (int_of_string a, Some (int_of_string b))
          | _ -> (-1, None)
        in
        if lo < 0 then begin
          Buffer.add_char buf c;
          incr i
        end else begin
          let atom = Buffer.sub buf !last_atom_start (!last_atom_end - !last_atom_start) in
          (* Drop the originally-emitted atom; we re-emit n copies below. *)
          let prefix = Buffer.sub buf 0 !last_atom_start in
          Buffer.clear buf;
          Buffer.add_string buf prefix;
          for _ = 1 to lo do Buffer.add_string buf atom done;
          (match hi with
           | None -> Buffer.add_string buf atom; Buffer.add_char buf '*'
           | Some hi ->
               for _ = 1 to hi - lo do
                 Buffer.add_string buf atom;
                 Buffer.add_char buf '?'
               done);
          last_atom_end := Buffer.length buf;
          last_atom_start := !last_atom_end - String.length atom;
          i := !j + 1
        end
      end else begin
        Buffer.add_char buf c;
        incr i
      end
    end
    else begin
      let atom_start_in_src = !i in
      (match find_atom_start (!i + 1) with
       | Some _ when c = '[' ->
           let depth = ref 1 in
           let j = ref (!i + 1) in
           while !j < n && !depth > 0 do
             let cj = s.[!j] in
             if cj = '\\' && !j + 1 < n then j := !j + 2
             else if cj = '[' then begin incr depth; incr j end
             else if cj = ']' then begin decr depth; incr j end
             else incr j
           done;
           Buffer.add_substring buf s atom_start_in_src (!j - atom_start_in_src);
           last_atom_start := Buffer.length buf - (!j - atom_start_in_src);
           last_atom_end := Buffer.length buf;
           i := !j
       | _ ->
           Buffer.add_char buf c;
           last_atom_start := Buffer.length buf - 1;
           last_atom_end := Buffer.length buf;
           incr i)
    end
  done;
  Buffer.contents buf

(* JSON array-of-keys helpers (Clojure get-in / Ruby dig style).
   Each segment is a typed value: VString → map key, VInt → array index.
   For arrays, VString segments that parse as int are accepted (this lets
   `(json_get j (split path "."))` work without manual int conversion).
   This avoids dot-path ambiguity (keys-with-dots, "0" vs 0). *)
let seg_label = function
  | VString s -> "\"" ^ s ^ "\""
  | VInt n -> Int64.to_string n
  | _ -> "<non-string-non-int>"

let json_step_into node seg =
  match node, seg with
  | VMap (m, _), VString k ->
      (try Hashtbl.find m k
       with Not_found -> raise (RuntimeError ("Key not found in JSON object: " ^ k)))
  | VMap _, VInt _ ->
      raise (RuntimeError ("Cannot index map with int segment " ^ seg_label seg))
  | VArray arr, VInt idx ->
      let i = Int64.to_int idx in
      if i >= 0 && i < Array.length !arr then !arr.(i)
      else raise (RuntimeError ("JSON array index out of bounds: " ^ Int64.to_string idx))
  | VArray arr, VString s ->
      (try
        let i = int_of_string s in
        if i >= 0 && i < Array.length !arr then !arr.(i)
        else raise (RuntimeError ("JSON array index out of bounds: " ^ s))
      with Failure _ ->
        raise (RuntimeError ("Cannot index array with non-integer segment: " ^ s)))
  | _ ->
      raise (RuntimeError ("Cannot descend into scalar at segment " ^ seg_label seg))

let json_walk_keys start keys =
  Array.fold_left json_step_into start keys

(* For set/delete: walk all but the final segment, return (parent, last_seg). *)
let json_walk_parent start keys =
  let n = Array.length keys in
  if n = 0 then (start, VUnit)
  else
    let init = Array.sub keys 0 (n - 1) in
    let last = keys.(n - 1) in
    (Array.fold_left json_step_into start init, last)

(* ===== BigDecimal: String-based arbitrary precision arithmetic ===== *)

(* Parse a decimal string into (negative, integer_digits, fractional_digits) *)
(* e.g. "-123.45" -> (true, "123", "45"), "0.1" -> (false, "0", "1") *)
let decimal_parse s =
  let s = String.trim s in
  let neg, s =
    if String.length s > 0 && s.[0] = '-' then (true, String.sub s 1 (String.length s - 1))
    else (false, s)
  in
  match String.split_on_char '.' s with
  | [int_part] -> (neg, int_part, "")
  | [int_part; frac_part] -> (neg, int_part, frac_part)
  | _ -> raise (RuntimeError ("Invalid decimal: " ^ s))

(* Pad fractional parts to same length *)
let decimal_align_frac f1 f2 =
  let len1 = String.length f1 and len2 = String.length f2 in
  let max_len = max len1 len2 in
  let pad s len = s ^ String.make (max_len - len) '0' in
  (pad f1 len1, pad f2 len2, max_len)

(* Remove leading zeros from integer part (keep at least "0") *)
let strip_leading_zeros s =
  let len = String.length s in
  let i = ref 0 in
  while !i < len - 1 && s.[!i] = '0' do incr i done;
  String.sub s !i (len - !i)

(* Remove trailing zeros from fractional part *)
let strip_trailing_zeros s =
  let len = String.length s in
  let i = ref (len - 1) in
  while !i >= 0 && s.[!i] = '0' do decr i done;
  if !i < 0 then "" else String.sub s 0 (!i + 1)

(* Normalize a decimal string: strip leading/trailing zeros *)
let decimal_normalize s =
  let (neg, int_part, frac_part) = decimal_parse s in
  let int_part = strip_leading_zeros int_part in
  let frac_part = strip_trailing_zeros frac_part in
  let is_zero = int_part = "0" && frac_part = "" in
  let sign = if neg && not is_zero then "-" else "" in
  if frac_part = "" then sign ^ int_part
  else sign ^ int_part ^ "." ^ frac_part

(* Compare absolute values of two non-negative decimal strings *)
(* Returns -1, 0, or 1 *)
let decimal_compare_abs i1 f1 i2 f2 =
  let i1 = strip_leading_zeros i1 and i2 = strip_leading_zeros i2 in
  let len1 = String.length i1 and len2 = String.length i2 in
  if len1 <> len2 then compare len1 len2
  else
    let c = String.compare i1 i2 in
    if c <> 0 then c
    else
      let (f1', f2', _) = decimal_align_frac f1 f2 in
      String.compare f1' f2'

(* Add two non-negative decimal digit strings (int_part, frac_part) *)
(* Returns (int_result, frac_result) *)
let decimal_add_unsigned i1 f1 i2 f2 =
  let (f1', f2', frac_len) = decimal_align_frac f1 f2 in
  (* Combine into full digit strings: int_part + frac_part *)
  let full1 = i1 ^ f1' and full2 = i2 ^ f2' in
  (* Pad to same length *)
  let max_len = max (String.length full1) (String.length full2) in
  let pad s = String.make (max_len - String.length s) '0' ^ s in
  let s1 = pad full1 and s2 = pad full2 in
  (* Add digit by digit from right *)
  let result = Bytes.make (max_len + 1) '0' in
  let carry = ref 0 in
  for i = max_len - 1 downto 0 do
    let d = Char.code s1.[i] - 48 + Char.code s2.[i] - 48 + !carry in
    Bytes.set result (i + 1) (Char.chr (48 + d mod 10));
    carry := d / 10
  done;
  if !carry > 0 then Bytes.set result 0 (Char.chr (48 + !carry));
  let full_result = Bytes.to_string result in
  let total_len = String.length full_result in
  let int_len = total_len - frac_len in
  let int_result = strip_leading_zeros (String.sub full_result 0 int_len) in
  let frac_result = if frac_len > 0 then String.sub full_result int_len frac_len else "" in
  (int_result, frac_result)

(* Subtract two non-negative decimals where a >= b *)
(* Returns (int_result, frac_result) *)
let decimal_sub_unsigned i1 f1 i2 f2 =
  let (f1', f2', frac_len) = decimal_align_frac f1 f2 in
  let full1 = i1 ^ f1' and full2 = i2 ^ f2' in
  let max_len = max (String.length full1) (String.length full2) in
  let pad s = String.make (max_len - String.length s) '0' ^ s in
  let s1 = pad full1 and s2 = pad full2 in
  let result = Bytes.make max_len '0' in
  let borrow = ref 0 in
  for i = max_len - 1 downto 0 do
    let d = Char.code s1.[i] - Char.code s2.[i] - !borrow in
    if d < 0 then begin
      Bytes.set result i (Char.chr (48 + d + 10));
      borrow := 1
    end else begin
      Bytes.set result i (Char.chr (48 + d));
      borrow := 0
    end
  done;
  let full_result = Bytes.to_string result in
  let total_len = String.length full_result in
  let int_len = total_len - frac_len in
  let int_result = strip_leading_zeros (String.sub full_result 0 int_len) in
  let frac_result = if frac_len > 0 then String.sub full_result int_len frac_len else "" in
  (int_result, frac_result)

(* Format (neg, int_part, frac_part) to decimal string *)
let decimal_format neg int_part frac_part =
  let frac_part = strip_trailing_zeros frac_part in
  let int_part = strip_leading_zeros int_part in
  let is_zero = int_part = "0" && frac_part = "" in
  let sign = if neg && not is_zero then "-" else "" in
  if frac_part = "" then sign ^ int_part
  else sign ^ int_part ^ "." ^ frac_part

(* BigDecimal addition *)
let bigdecimal_add a b =
  let (neg_a, ia, fa) = decimal_parse a in
  let (neg_b, ib, fb) = decimal_parse b in
  match neg_a, neg_b with
  | false, false ->
      let (ri, rf) = decimal_add_unsigned ia fa ib fb in
      decimal_format false ri rf
  | true, true ->
      let (ri, rf) = decimal_add_unsigned ia fa ib fb in
      decimal_format true ri rf
  | false, true ->
      let cmp = decimal_compare_abs ia fa ib fb in
      if cmp >= 0 then
        let (ri, rf) = decimal_sub_unsigned ia fa ib fb in
        decimal_format false ri rf
      else
        let (ri, rf) = decimal_sub_unsigned ib fb ia fa in
        decimal_format true ri rf
  | true, false ->
      let cmp = decimal_compare_abs ia fa ib fb in
      if cmp > 0 then
        let (ri, rf) = decimal_sub_unsigned ia fa ib fb in
        decimal_format true ri rf
      else
        let (ri, rf) = decimal_sub_unsigned ib fb ia fa in
        decimal_format false ri rf

(* BigDecimal subtraction: a - b = a + (-b) *)
let bigdecimal_sub a b =
  let (neg_b, ib, fb) = decimal_parse b in
  let neg_b' = not neg_b in
  let b' = decimal_format neg_b' ib fb in
  bigdecimal_add a b'

(* BigDecimal multiplication *)
let bigdecimal_mul a b =
  let (neg_a, ia, fa) = decimal_parse a in
  let (neg_b, ib, fb) = decimal_parse b in
  let frac_places = String.length fa + String.length fb in
  (* Multiply as integers *)
  let num_a = ia ^ fa and num_b = ib ^ fb in
  let len_a = String.length num_a and len_b = String.length num_b in
  let result_len = len_a + len_b in
  let result = Array.make result_len 0 in
  for i = len_a - 1 downto 0 do
    let da = Char.code num_a.[i] - 48 in
    for j = len_b - 1 downto 0 do
      let db = Char.code num_b.[j] - 48 in
      let pos = (len_a - 1 - i) + (len_b - 1 - j) in
      result.(pos) <- result.(pos) + da * db
    done
  done;
  (* Carry propagation *)
  for i = 0 to result_len - 2 do
    result.(i + 1) <- result.(i + 1) + result.(i) / 10;
    result.(i) <- result.(i) mod 10
  done;
  (* Convert to string (reversed) *)
  let buf = Buffer.create result_len in
  let started = ref false in
  for i = result_len - 1 downto 0 do
    if result.(i) <> 0 then started := true;
    if !started then Buffer.add_char buf (Char.chr (result.(i) + 48))
  done;
  let digits = if Buffer.length buf = 0 then "0" else Buffer.contents buf in
  (* Insert decimal point *)
  let total_digits = String.length digits in
  let result_neg = neg_a <> neg_b in
  if frac_places = 0 then
    decimal_format result_neg digits ""
  else if total_digits <= frac_places then
    let padded = String.make (frac_places - total_digits) '0' ^ digits in
    decimal_format result_neg "0" padded
  else
    let int_part = String.sub digits 0 (total_digits - frac_places) in
    let frac_part = String.sub digits (total_digits - frac_places) frac_places in
    decimal_format result_neg int_part frac_part

(* BigDecimal division with specified precision *)
let bigdecimal_div a b ?(precision=20) () =
  let (neg_a, ia, fa) = decimal_parse a in
  let (neg_b, ib, fb) = decimal_parse b in
  (* Check for division by zero *)
  let b_is_zero = strip_leading_zeros ib = "0" && strip_trailing_zeros fb = "" in
  if b_is_zero then raise (RuntimeError "Division by zero");
  (* Convert to integers by removing decimal points *)
  let num_a = ia ^ fa and num_b = ib ^ fb in
  let scale_diff = String.length fa - String.length fb in
  (* We need: (num_a / num_b) * 10^(-scale_diff) *)
  (* Shift num_a by (precision + scale_diff) to get enough digits *)
  let extra_zeros = precision + (if scale_diff < 0 then -scale_diff else 0) in
  let shifted_a = num_a ^ String.make extra_zeros '0' in
  (* Long division on digit strings *)
  let dividend = ref (strip_leading_zeros shifted_a) in
  let divisor = strip_leading_zeros num_b in
  let divisor_len = String.length divisor in
  (* Simple long division: repeatedly subtract *)
  let quotient = Buffer.create 32 in
  let remainder = Buffer.create 32 in
  Buffer.add_string remainder "";
  let rem = ref "" in
  for i = 0 to String.length !dividend - 1 do
    (* Bring down next digit *)
    rem := strip_leading_zeros (!rem ^ String.make 1 !dividend.[i]);
    (* Count how many times divisor goes into remainder *)
    let count = ref 0 in
    let cur_rem = ref !rem in
    let continue_loop = ref true in
    while !continue_loop do
      let rem_len = String.length !cur_rem in
      if rem_len < divisor_len then
        continue_loop := false
      else if rem_len > divisor_len then begin
        (* Remainder is larger, can subtract *)
        (* Do subtraction *)
        let sub_result = Bytes.make rem_len '0' in
        let borrow = ref 0 in
        let padded_div = String.make (rem_len - divisor_len) '0' ^ divisor in
        for j = rem_len - 1 downto 0 do
          let d = Char.code !cur_rem.[j] - Char.code padded_div.[j] - !borrow in
          if d < 0 then begin
            Bytes.set sub_result j (Char.chr (48 + d + 10));
            borrow := 1
          end else begin
            Bytes.set sub_result j (Char.chr (48 + d));
            borrow := 0
          end
        done;
        cur_rem := strip_leading_zeros (Bytes.to_string sub_result);
        incr count
      end else begin
        (* Same length, compare *)
        if String.compare !cur_rem divisor >= 0 then begin
          let sub_result = Bytes.make rem_len '0' in
          let borrow = ref 0 in
          for j = rem_len - 1 downto 0 do
            let d = Char.code !cur_rem.[j] - Char.code divisor.[j] - !borrow in
            if d < 0 then begin
              Bytes.set sub_result j (Char.chr (48 + d + 10));
              borrow := 1
            end else begin
              Bytes.set sub_result j (Char.chr (48 + d));
              borrow := 0
            end
          done;
          cur_rem := strip_leading_zeros (Bytes.to_string sub_result);
          incr count
        end else
          continue_loop := false
      end
    done;
    Buffer.add_char quotient (Char.chr (48 + !count));
    rem := !cur_rem
  done;
  ignore remainder;
  let q_str = strip_leading_zeros (Buffer.contents quotient) in
  (* The result has (precision + max(0, -scale_diff)) fractional digits *)
  (* But we also need to account for scale_diff *)
  let frac_digits = precision + (if scale_diff > 0 then scale_diff else 0) in
  let total_digits = String.length q_str in
  let result_neg = neg_a <> neg_b in
  if total_digits <= frac_digits then
    let padded = String.make (frac_digits - total_digits) '0' ^ q_str in
    decimal_format result_neg "0" padded
  else
    let int_part = String.sub q_str 0 (total_digits - frac_digits) in
    let frac_part = String.sub q_str (total_digits - frac_digits) frac_digits in
    decimal_format result_neg int_part frac_part

(* BigDecimal negation *)
let bigdecimal_neg a =
  let (neg, i, f) = decimal_parse a in
  let is_zero = strip_leading_zeros i = "0" && strip_trailing_zeros f = "" in
  if is_zero then a
  else decimal_format (not neg) i f

(* BigDecimal absolute value *)
let bigdecimal_abs a =
  let (_, i, f) = decimal_parse a in
  decimal_format false i f

(* BigDecimal comparison: returns -1, 0, 1 *)
let bigdecimal_compare a b =
  let (neg_a, ia, fa) = decimal_parse a in
  let (neg_b, ib, fb) = decimal_parse b in
  let a_zero = strip_leading_zeros ia = "0" && strip_trailing_zeros fa = "" in
  let b_zero = strip_leading_zeros ib = "0" && strip_trailing_zeros fb = "" in
  if a_zero && b_zero then 0
  else match neg_a, neg_b with
  | false, true -> 1
  | true, false -> -1
  | false, false -> decimal_compare_abs ia fa ib fb
  | true, true -> -(decimal_compare_abs ia fa ib fb)

(* Helper to format decimal values - now just normalizes *)
let format_decimal f =
  let s = string_of_float f in
  if String.ends_with ~suffix:"." s then
    String.sub s 0 (String.length s - 1)
  else s

(* Helper to format float-to-string - preserves .0 for whole numbers *)
let format_float_string f =
  let s = string_of_float f in
  if String.ends_with ~suffix:"." s then
    s ^ "0"
  else s

(* ---- SHA-1 implementation (RFC 3174) ---- *)
let sha1 (msg : string) : string =
  let open Int32 in
  let ( +: ) = add and ( &: ) = logand and ( |: ) = logor
  and ( ^: ) = logxor and ( <<: ) a n = shift_left a n
  and ( >>: ) a n = shift_right_logical a n in
  let rotl a n = (a <<: n) |: (a >>: (32 - n)) in
  let msg_len = String.length msg in
  let bit_len = msg_len * 8 in
  (* Padding: msg + 0x80 + zeros + 8-byte big-endian length *)
  let pad_len =
    let r = (msg_len + 1) mod 64 in
    if r <= 56 then 56 - r else 120 - r
  in
  let total = msg_len + 1 + pad_len + 8 in
  let buf = Bytes.make total '\x00' in
  Bytes.blit_string msg 0 buf 0 msg_len;
  Bytes.set buf msg_len '\x80';
  (* Big-endian 64-bit length at the end (only lower 32 bits needed here) *)
  Bytes.set buf (total - 4) (Char.chr ((bit_len lsr 24) land 0xFF));
  Bytes.set buf (total - 3) (Char.chr ((bit_len lsr 16) land 0xFF));
  Bytes.set buf (total - 2) (Char.chr ((bit_len lsr 8) land 0xFF));
  Bytes.set buf (total - 1) (Char.chr (bit_len land 0xFF));
  let h0 = ref 0x67452301l and h1 = ref 0xEFCDAB89l
  and h2 = ref 0x98BADCFEl and h3 = ref 0x10325476l
  and h4 = ref 0xC3D2E1F0l in
  let w = Array.make 80 0l in
  let nblocks = total / 64 in
  for blk = 0 to nblocks - 1 do
    let off = blk * 64 in
    for i = 0 to 15 do
      let b0 = of_int (Char.code (Bytes.get buf (off + i*4))) in
      let b1 = of_int (Char.code (Bytes.get buf (off + i*4+1))) in
      let b2 = of_int (Char.code (Bytes.get buf (off + i*4+2))) in
      let b3 = of_int (Char.code (Bytes.get buf (off + i*4+3))) in
      w.(i) <- (b0 <<: 24) |: (b1 <<: 16) |: (b2 <<: 8) |: b3
    done;
    for i = 16 to 79 do
      w.(i) <- rotl (w.(i-3) ^: w.(i-8) ^: w.(i-14) ^: w.(i-16)) 1
    done;
    let a = ref !h0 and b = ref !h1 and c = ref !h2
    and d = ref !h3 and e = ref !h4 in
    for i = 0 to 79 do
      let f, k =
        if i < 20 then ((!b &: !c) |: ((lognot !b) &: !d)), 0x5A827999l
        else if i < 40 then (!b ^: !c ^: !d), 0x6ED9EBA1l
        else if i < 60 then ((!b &: !c) |: (!b &: !d) |: (!c &: !d)), 0x8F1BBCDCl
        else (!b ^: !c ^: !d), 0xCA62C1D6l
      in
      let temp = (rotl !a 5) +: f +: !e +: k +: w.(i) in
      e := !d; d := !c; c := rotl !b 30; b := !a; a := temp
    done;
    h0 := !h0 +: !a; h1 := !h1 +: !b; h2 := !h2 +: !c;
    h3 := !h3 +: !d; h4 := !h4 +: !e
  done;
  (* Output 20 bytes *)
  let out = Bytes.create 20 in
  let put32 off v =
    Bytes.set out off (Char.chr (to_int ((v >>: 24) &: 0xFFl)));
    Bytes.set out (off+1) (Char.chr (to_int ((v >>: 16) &: 0xFFl)));
    Bytes.set out (off+2) (Char.chr (to_int ((v >>: 8) &: 0xFFl)));
    Bytes.set out (off+3) (Char.chr (to_int (v &: 0xFFl)))
  in
  put32 0 !h0; put32 4 !h1; put32 8 !h2; put32 12 !h3; put32 16 !h4;
  Bytes.to_string out

(* ---- Base64 encode ---- *)
let base64_encode (data : string) : string =
  let tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" in
  let len = String.length data in
  let buf = Buffer.create ((len + 2) / 3 * 4) in
  let i = ref 0 in
  while !i < len do
    let b0 = Char.code data.[!i] in
    let b1 = if !i + 1 < len then Char.code data.[!i + 1] else 0 in
    let b2 = if !i + 2 < len then Char.code data.[!i + 2] else 0 in
    Buffer.add_char buf tbl.[(b0 lsr 2) land 0x3F];
    Buffer.add_char buf tbl.[((b0 lsl 4) lor (b1 lsr 4)) land 0x3F];
    if !i + 1 < len then
      Buffer.add_char buf tbl.[((b1 lsl 2) lor (b2 lsr 6)) land 0x3F]
    else
      Buffer.add_char buf '=';
    if !i + 2 < len then
      Buffer.add_char buf tbl.[b2 land 0x3F]
    else
      Buffer.add_char buf '=';
    i := !i + 3
  done;
  Buffer.contents buf

(* ---- WebSocket helpers ---- *)
let ws_magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

(* Read exactly n bytes from a transport *)
let ws_read_exact transport n =
  let buf = Bytes.create n in
  let pos = ref 0 in
  while !pos < n do
    let got = match transport with
      | WsPlain fd -> Unix.read fd buf !pos (n - !pos)
      | WsTls ssl -> Ssl.read ssl buf !pos (n - !pos)
    in
    if got = 0 then raise (RuntimeError "WebSocket: connection closed");
    pos := !pos + got
  done;
  Bytes.to_string buf

let ws_write transport data =
  let len = String.length data in
  let _ = match transport with
    | WsPlain fd -> Unix.write_substring fd data 0 len
    | WsTls ssl -> Ssl.write_substring ssl data 0 len
  in ()

(* Server-side handshake: read HTTP request, extract key, send response *)
let ws_server_handshake transport =
  (* Read HTTP upgrade request *)
  let buf = Buffer.create 1024 in
  let found = ref false in
  while not !found do
    let ch = ws_read_exact transport 1 in
    Buffer.add_string buf ch;
    let s = Buffer.contents buf in
    let slen = String.length s in
    if slen >= 4 && String.sub s (slen - 4) 4 = "\r\n\r\n" then
      found := true
  done;
  let request = Buffer.contents buf in
  (* Extract Sec-WebSocket-Key *)
  let key = ref "" in
  let lines = String.split_on_char '\n' request in
  List.iter (fun line ->
    let line = String.trim line in
    let prefix = "Sec-WebSocket-Key:" in
    let plen = String.length prefix in
    if String.length line >= plen &&
       String.lowercase_ascii (String.sub line 0 plen) = String.lowercase_ascii prefix then
      key := String.trim (String.sub line plen (String.length line - plen))
  ) lines;
  if !key = "" then raise (RuntimeError "WebSocket: no Sec-WebSocket-Key in handshake");
  (* Compute accept hash *)
  let accept_raw = sha1 (!key ^ ws_magic) in
  let accept_b64 = base64_encode accept_raw in
  (* Send response *)
  let resp = "HTTP/1.1 101 Switching Protocols\r\n" ^
             "Upgrade: websocket\r\n" ^
             "Connection: Upgrade\r\n" ^
             "Sec-WebSocket-Accept: " ^ accept_b64 ^ "\r\n\r\n" in
  ws_write transport resp

(* Client-side handshake *)
let ws_client_handshake transport host path =
  let ws_key = base64_encode "sigil-ws-key-000" in
  let req = "GET " ^ path ^ " HTTP/1.1\r\n" ^
            "Host: " ^ host ^ "\r\n" ^
            "Upgrade: websocket\r\n" ^
            "Connection: Upgrade\r\n" ^
            "Sec-WebSocket-Key: " ^ ws_key ^ "\r\n" ^
            "Sec-WebSocket-Version: 13\r\n\r\n" in
  ws_write transport req;
  (* Read response until \r\n\r\n *)
  let buf = Buffer.create 1024 in
  let found = ref false in
  while not !found do
    let ch = ws_read_exact transport 1 in
    Buffer.add_string buf ch;
    let s = Buffer.contents buf in
    let slen = String.length s in
    if slen >= 4 && String.sub s (slen - 4) 4 = "\r\n\r\n" then
      found := true
  done

(* Encode a text frame (server sends unmasked) *)
let ws_encode_frame ?(masked=false) msg =
  let len = String.length msg in
  let buf = Buffer.create (len + 14) in
  (* FIN=1, opcode=1 (text) *)
  Buffer.add_char buf (Char.chr 0x81);
  let mask_bit = if masked then 0x80 else 0 in
  if len < 126 then
    Buffer.add_char buf (Char.chr (mask_bit lor len))
  else if len < 65536 then begin
    Buffer.add_char buf (Char.chr (mask_bit lor 126));
    Buffer.add_char buf (Char.chr ((len lsr 8) land 0xFF));
    Buffer.add_char buf (Char.chr (len land 0xFF))
  end else begin
    Buffer.add_char buf (Char.chr (mask_bit lor 127));
    for i = 7 downto 0 do
      Buffer.add_char buf (Char.chr ((len lsr (i * 8)) land 0xFF))
    done
  end;
  if masked then begin
    (* Use zero mask for simplicity *)
    Buffer.add_string buf "\x00\x00\x00\x00";
  end;
  Buffer.add_string buf msg;
  Buffer.contents buf

(* Decode a WebSocket frame, returns (opcode, payload) *)
let ws_decode_frame transport =
  let hdr = ws_read_exact transport 2 in
  let b0 = Char.code hdr.[0] and b1 = Char.code hdr.[1] in
  let opcode = b0 land 0x0F in
  let is_masked = (b1 land 0x80) <> 0 in
  let payload_len = b1 land 0x7F in
  let actual_len =
    if payload_len = 126 then begin
      let ext = ws_read_exact transport 2 in
      (Char.code ext.[0] lsl 8) lor (Char.code ext.[1])
    end else if payload_len = 127 then begin
      let ext = ws_read_exact transport 8 in
      (* Only handle up to max_int for OCaml *)
      let len = ref 0 in
      for i = 0 to 7 do
        len := (!len lsl 8) lor (Char.code ext.[i])
      done;
      !len
    end else
      payload_len
  in
  let mask =
    if is_masked then Some (ws_read_exact transport 4) else None
  in
  let payload = ws_read_exact transport actual_len in
  let unmasked = match mask with
    | None -> payload
    | Some m ->
        let b = Bytes.of_string payload in
        for i = 0 to actual_len - 1 do
          let c = Char.code (Bytes.get b i) lxor Char.code m.[i mod 4] in
          Bytes.set b i (Char.chr c)
        done;
        Bytes.to_string b
  in
  (opcode, unmasked)

(* Send a close frame *)
let ws_send_close transport ~masked =
  let buf = Buffer.create 6 in
  Buffer.add_char buf (Char.chr 0x88);  (* FIN=1, opcode=8 close *)
  if masked then begin
    Buffer.add_char buf (Char.chr 0x80);  (* masked, length=0 *)
    Buffer.add_string buf "\x00\x00\x00\x00"
  end else
    Buffer.add_char buf (Char.chr 0x00);  (* unmasked, length=0 *)
  ws_write transport (Buffer.contents buf)


(* String representation of values *)
let rec string_of_value = function
  | VInt n -> Int64.to_string n
  | VFloat f -> format_float_string f
  | VDecimal s -> s
  | VString s -> s
  | VBool b -> string_of_bool b
   | VUnit -> "unit"
   | VArray arr ->
       let vals = Array.to_list !arr in
       "[" ^ String.concat ", " (List.map string_of_value vals) ^ "]"
   | VMap _ -> "<map>"
   | VFunction (name, _, _, _) -> "<function:" ^ name ^ ">"
   | VSocket _ -> "<socket>"
   | VTlsSocket _ -> "<tls_socket>"
   | VWsSocket _ -> "<ws_socket>"
   | VChannel _ -> "<channel>"
   | VProcess pid -> "<process:" ^ string_of_int pid ^ ">"

(* Recursive structural equality for all value types *)
let rec values_equal v1 v2 =
  match v1, v2 with
  | VInt a, VInt b -> a = b
  | VFloat a, VFloat b -> a = b
  | VDecimal s1, VDecimal s2 -> bigdecimal_compare s1 s2 = 0
  | VString a, VString b -> a = b
  | VBool a, VBool b -> a = b
  | VUnit, VUnit -> true
  | VArray a, VArray b ->
      let a' = !a and b' = !b in
      Array.length a' = Array.length b' &&
      let rec check i =
        if i >= Array.length a' then true
        else values_equal a'.(i) b'.(i) && check (i + 1)
      in check 0
  | VMap (m1, keys1), VMap (m2, keys2) ->
      let k1 = !keys1 and k2 = !keys2 in
      List.length k1 = List.length k2 &&
      List.for_all (fun k ->
        Hashtbl.mem m2 k &&
        values_equal (Hashtbl.find m1 k) (Hashtbl.find m2 k)
      ) k1 &&
      List.for_all (fun k -> Hashtbl.mem m1 k) k2
  | _ -> false

(* Deep copy a value (recursive for arrays and maps) *)
let rec deep_copy_value v =
  match v with
  | VArray arr ->
      VArray (ref (Array.map deep_copy_value !arr))
  | VMap (m, keys) ->
      let new_m = Hashtbl.create (Hashtbl.length m) in
      List.iter (fun k ->
        Hashtbl.replace new_m k (deep_copy_value (Hashtbl.find m k))
      ) !keys;
      VMap (new_m, ref (List.map Fun.id !keys))
  | _ -> v  (* Primitives are immutable, no need to copy *)

(* Evaluate expression *)
let rec eval env expr =
  match expr with
  | LitInt n -> VInt n
  | LitFloat f -> VFloat f
  | LitDecimal s -> VDecimal s
  | LitString s -> VString s
   | LitBool b -> VBool b
   | LitUnit -> VUnit

   | Var name ->
       (try env_get env name
        with RuntimeError _ ->
          (* Name isn't in scope — treat as a first-class reference to a
             builtin. Wrapping is lazy; errors surface only if it's actually
             called. This lets `(reduce + 0 xs)` or `(map_arr xs int)` work. *)
          VBuiltin name)

  | Call ("fmt", fmt_args) when (match fmt_args with LitString _ :: _ -> true | _ -> false) ->
      (* Special form: scan template for {var} (scope lookup) and {} (positional from args).
         First arg is the template, remaining args fill {} placeholders in order.
         Also accepts Python-style format specs: {:.3f} {:>5} {:0>5} {:<10} {:^6}
         {:b} {:x} — alignment, width, precision, type. The full grammar:
            [name][:[fill][align][0][width][.precision][type]]
         Examples: {:.3f}, {x:>5}, {:0>4d}, {name}, {}. *)
      let (template, extra_args) = match fmt_args with
        | LitString t :: rest -> (t, List.map (eval env) rest)
        | _ -> assert false
      in
      let buf = Buffer.create (String.length template) in
      let len = String.length template in
      let i = ref 0 in
      let positional = ref extra_args in
      (* Parse a Python-shaped format spec (the part after the colon). *)
      let parse_spec spec =
        let n = String.length spec in
        let p = ref 0 in
        let fill = ref ' ' and align = ref ' ' in
        if n >= 2 && (spec.[1] = '<' || spec.[1] = '>' || spec.[1] = '^') then begin
          fill := spec.[0]; align := spec.[1]; p := 2
        end else if n >= 1 && (spec.[0] = '<' || spec.[0] = '>' || spec.[0] = '^') then begin
          align := spec.[0]; p := 1
        end;
        if !p < n && spec.[!p] = '0' && !align = ' ' then begin
          fill := '0'; align := '>'; incr p
        end;
        let ws = !p in
        while !p < n && spec.[!p] >= '0' && spec.[!p] <= '9' do incr p done;
        let width = if !p > ws then int_of_string (String.sub spec ws (!p - ws)) else 0 in
        let precision = ref (-1) in
        if !p < n && spec.[!p] = '.' then begin
          incr p;
          let ps = !p in
          while !p < n && spec.[!p] >= '0' && spec.[!p] <= '9' do incr p done;
          if !p > ps then precision := int_of_string (String.sub spec ps (!p - ps))
        end;
        let ty = if !p < n then spec.[!p] else ' ' in
        (!fill, !align, width, !precision, ty)
      in
      let pad_to fill align width s =
        let l = String.length s in
        if l >= width then s
        else
          let pad = String.make (width - l) fill in
          (match align with
           | '<' -> s ^ pad
           | '^' ->
               let left = (width - l) / 2 in
               let right = (width - l) - left in
               String.make left fill ^ s ^ String.make right fill
           | _ (* '>' default *) -> pad ^ s)
      in
      let format_with_spec v spec =
        let (fill, align, width, precision, ty) = parse_spec spec in
        let body = match ty, v with
          | 'f', VFloat f -> Printf.sprintf "%.*f" (max 0 (if precision >= 0 then precision else 6)) f
          | 'f', VInt n  -> Printf.sprintf "%.*f" (max 0 (if precision >= 0 then precision else 6)) (Int64.to_float n)
          | 'd', VInt n  -> Int64.to_string n
          | 'd', VFloat f -> Int64.to_string (Int64.of_float f)
          | 'x', VInt n  -> Printf.sprintf "%Lx" n
          | 'X', VInt n  -> Printf.sprintf "%LX" n
          | 'o', VInt n  -> Printf.sprintf "%Lo" n
          | 'b', VInt n  -> let rec b acc x = if x = 0L then (if acc = "" then "0" else acc) else b ((if Int64.rem x 2L = 0L then "0" else "1") ^ acc) (Int64.div x 2L) in b "" n
          | 's', _ -> string_of_value v
          | ' ', VFloat f when precision >= 0 -> Printf.sprintf "%.*f" precision f
          | ' ', VInt n when precision >= 0 -> Printf.sprintf "%.*f" precision (Int64.to_float n)
          | _, _ -> string_of_value v
        in
        let align' = if align = ' ' then '>' else align in
        pad_to fill align' width body
      in
      let consume_positional ?(spec="") () =
        match !positional with
        | v :: rest ->
            Buffer.add_string buf (if spec = "" then string_of_value v else format_with_spec v spec);
            positional := rest
        | [] -> Buffer.add_string buf "{}"  (* lenient: leave a marker *)
      in
      let _ = consume_positional in  (* suppress unused warning if any branch doesn't use *)
      while !i < len do
        let c = template.[!i] in
        if c = '{' && !i + 1 < len && template.[!i + 1] = '{' then begin
          Buffer.add_char buf '{';
          i := !i + 2
        end else if c = '}' && !i + 1 < len && template.[!i + 1] = '}' then begin
          Buffer.add_char buf '}';
          i := !i + 2
        end else if c = '%' && !i + 1 < len && template.[!i + 1] = '%' then begin
          (* Escaped literal percent: %% → % *)
          Buffer.add_char buf '%';
          i := !i + 2
        end else if c = '%' && !i + 1 < len &&
                    (let n = template.[!i + 1] in
                     n = 's' || n = 'd' || n = 'i' || n = 'f' || n = 'g' ||
                     n = 'x' || n = 'o' || n = 'b' || n = 'v') then begin
          (* Printf-style positional placeholder: %s %d %f ... — all behave
             the same in Sigil (string-of-value of the next arg). Accepted as
             a Python/C ergonomics alias since LLMs trained on those reach
             for printf style by default. *)
          consume_positional ();
          i := !i + 2
        end else if c = '{' then begin
          let close = try String.index_from template (!i + 1) '}' with Not_found -> -1 in
          if close = -1 then begin
            Buffer.add_char buf c;
            incr i
          end else begin
            let body = String.sub template (!i + 1) (close - !i - 1) in
            (* Split on first ':' to separate name from format spec *)
            let (name, spec) =
              try
                let colon = String.index body ':' in
                (String.sub body 0 colon,
                 String.sub body (colon + 1) (String.length body - colon - 1))
              with Not_found -> (body, "")
            in
            if name = "" then consume_positional ~spec ()
            else begin
              let v = env_get env name in
              Buffer.add_string buf
                (if spec = "" then string_of_value v else format_with_spec v spec)
            end;
            i := close + 1
          end
        end else begin
          Buffer.add_char buf c;
          incr i
        end
      done;
      VString (Buffer.contents buf)

  | Call (func_name, args) ->
      eval_call env func_name args
  
  | Set (var_name, var_type_opt, value_expr) ->
      let value = eval env value_expr in
      let type_of_value v = match v with
        | VInt _ -> TInt | VFloat _ -> TFloat | VDecimal _ -> TDecimal
        | VString _ -> TString | VBool _ -> TBool | VUnit -> TUnit
        | VArray _ -> TArray TUnit | VMap _ -> TMap (TUnit, TUnit)
        | VFunction _ | VClosure _ | VBuiltin _ -> TFunction ([], TUnit)
        | VSocket _ | VTlsSocket _ | VWsSocket _ -> TSocket
        | VChannel _ -> TSocket | VProcess _ -> TProcess
      in
      let var_type = match var_type_opt with
        | Some t -> t
        | None ->
            (* Try reassignment first (use existing variable's type) *)
            (try
              let existing = env_get env var_name in
              type_of_value existing
            with RuntimeError _ ->
              (* New declaration: infer from the value itself *)
              type_of_value value)
      in
      if not (type_matches var_type value) then begin
        (* Numeric widening: int → float → decimal is automatic on rebind.
           This addresses the common "declared as int but got float" trip
           where a model accumulates numeric updates. Non-numeric types
           keep their lock. *)
        let widened = match var_type, value with
          | TFloat, VInt n -> Some (VFloat (Int64.to_float n))
          | TDecimal, VInt n -> Some (VDecimal (Int64.to_string n))
          | TDecimal, VFloat f -> Some (VDecimal (format_float_string f))
          | _ -> None
        in
        match widened with
        | Some v ->
            env_set env var_name v;
            VUnit
        | None ->
            raise (RuntimeError (
              "Type mismatch: variable '" ^ var_name ^
              "' declared as " ^ string_of_type_kind var_type ^
              " but got " ^ string_of_value_type value))
      end
      else begin
        env_set env var_name value;
        VUnit
      end
  
  | Return expr -> raise (Return (eval env expr))
  | Break -> raise Break
  | Continue -> raise Continue
  | Label _ -> VUnit
  | Goto label_name -> raise (GotoLabel label_name)
  | IfNot (cond, label_name) ->
      (match eval env cond with
       | VBool false -> raise (GotoLabel label_name)
       | VBool true -> VUnit
       | _ -> raise (RuntimeError "IfNot condition must be boolean"))
  
  | If (cond, then_body, else_body) ->
      (match eval env cond with
       | VBool true -> eval_block env then_body
       | VBool false ->
           (match else_body with
            | Some body -> eval_block env body
            | None -> VUnit)
        | _ -> raise (RuntimeError "If condition must be boolean"))

  | Cond branches ->
      let rec try_branches = function
        | [] -> VUnit  (* no branch matched *)
        | (cond, body) :: rest ->
            (match eval env cond with
             | VBool true -> eval_block env body
             | VBool false -> try_branches rest
             | _ -> raise (RuntimeError "Cond branch condition must be boolean"))
      in
      try_branches branches

  | LitArray elems ->
      let vals = List.map (eval env) elems in
      VArray (ref (Array.of_list vals))

  | LitMap pairs ->
      let tbl = Hashtbl.create (List.length pairs) in
      let keys = ref [] in
      List.iter (fun (k_expr, v_expr) ->
        let key = match eval env k_expr with
          | VString s -> s
          | _ -> raise (RuntimeError "Map literal keys must be strings")
        in
        Hashtbl.replace tbl key (eval env v_expr);
        if not (List.mem key !keys) then
          keys := !keys @ [key]
      ) pairs;
      VMap (tbl, keys)

  | Lambda (params, body) ->
      (* Capture the current env as a snapshot. We copy non-function bindings only —
         functions are global and don't need closure semantics. *)
      let snapshot = Hashtbl.fold (fun k v acc ->
        match v with
        | VFunction _ -> acc  (* skip — already accessible *)
        | _ -> (k, v) :: acc
      ) env [] in
      VClosure (params, body, snapshot)

  | And (left, right) ->
      (match eval env left with
       | VBool false -> VBool false
       | VBool true ->
           (match eval env right with
            | VBool b -> VBool b
            | _ -> raise (RuntimeError "Invalid right operand for and: expected bool"))
       | _ -> raise (RuntimeError "Invalid left operand for and: expected bool"))

  | Or (left, right) ->
      (match eval env left with
       | VBool true -> VBool true
       | VBool false ->
           (match eval env right with
            | VBool b -> VBool b
            | _ -> raise (RuntimeError "Invalid right operand for or: expected bool"))
       | _ -> raise (RuntimeError "Invalid left operand for or: expected bool"))
  
  | While (cond, body) ->
      let rec loop () =
        match eval env cond with
        | VBool true ->
            (try 
              let _ = eval_block env body in
              loop ()
            with Break -> VUnit
               | Continue -> loop ())
        | VBool false -> VUnit
        | _ -> raise (RuntimeError "While condition must be boolean")
      in
      loop ()
  
  | Loop body ->
      let rec loop () =
        try
          let _ = eval_block env body in
          loop ()
        with Break -> VUnit
           | Continue -> loop ()
      in
      loop ()

  | For (var_name, start_expr, end_expr, body) ->
      let start_val = eval env start_expr in
      let end_val = eval env end_expr in
      (match start_val, end_val with
       | VInt s, VInt e ->
           let i = ref s in
           env_set env var_name (VInt !i);
           (try
             while Int64.compare !i e < 0 do
               env_set env var_name (VInt !i);
               (try
                 let _ = eval_block env body in ()
               with Continue -> ());
               (* Detect in-body mutation of the iterator. Silent rebinding
                  surprises models from C/Python where (set i ...) inside
                  for would alter iteration. We raise a clear error so the
                  validator-in-loop can hint toward (while) for variable-
                  stride / skip loops. *)
               (match env_get env var_name with
                | VInt v when Int64.compare v !i <> 0 ->
                    raise (RuntimeError
                      ("for-loop iterator '" ^ var_name ^
                       "' was mutated inside the body (set to " ^
                       Int64.to_string v ^ ", expected " ^
                       Int64.to_string !i ^
                       "). Use (while) for variable-stride or skip loops."))
                | _ -> ());
               i := Int64.add !i 1L
             done;
             VUnit
           with Break -> VUnit)
       | _ -> raise (RuntimeError "for loop start and end must be integers"))

  | ForEach (var_name, var_type, collection_expr, body) ->
      let coll = eval env collection_expr in
      (* TUnit means "no type annotation given" — skip the element type check *)
      let skip_check = (var_type = TUnit) in
      (match coll with
       | VArray arr ->
           let len = Array.length !arr in
           let i = ref 0 in
           (try
             while !i < len do
               let elem = !arr.(!i) in
               if (not skip_check) && not (type_matches var_type elem) then
                 raise (RuntimeError (
                   "Type mismatch in for-each: variable '" ^ var_name ^
                   "' declared as " ^ string_of_type_kind var_type ^
                   " but got " ^ string_of_value_type elem));
               env_set env var_name elem;
               (try
                 let _ = eval_block env body in ()
               with Continue -> ());
               i := !i + 1
             done;
             VUnit
           with Break -> VUnit)
       | VMap (_, keys) ->
           (try
             List.iter (fun k ->
               let key_val = VString k in
               if not (type_matches var_type key_val) then
                 raise (RuntimeError (
                   "Type mismatch in for-each: variable '" ^ var_name ^
                   "' declared as " ^ string_of_type_kind var_type ^
                   " but got " ^ string_of_value_type key_val));
               env_set env var_name key_val;
               (try
                 let _ = eval_block env body in ()
               with Continue -> ())
             ) !keys;
             VUnit
           with Break -> VUnit)
       | VString s ->
           (* for-each on a string iterates per-character (each as a 1-char
              string). Same convention as map_arr/filter polymorphism — the
              alternative is a less-friendly error and a forced (chars s)
              wrap that the model often forgets. *)
           let n = String.length s in
           let i = ref 0 in
           (try
             while !i < n do
               let elem = VString (String.make 1 s.[!i]) in
               if (not skip_check) && not (type_matches var_type elem) then
                 raise (RuntimeError (
                   "Type mismatch in for-each: variable '" ^ var_name ^
                   "' declared as " ^ string_of_type_kind var_type ^
                   " but got string (per-char iteration)"));
               env_set env var_name elem;
               (try
                 let _ = eval_block env body in ()
               with Continue -> ());
               i := !i + 1
             done;
             VUnit
           with Break -> VUnit)
       | _ -> raise (RuntimeError "for-each requires an array, map, or string"))

  | Try (try_body, catch_var, _catch_type, catch_body) ->
      (try
        eval_block env try_body
      with RuntimeError msg ->
        env_set env catch_var (VString msg);
        eval_block env catch_body)

and eval_block env exprs =
  let arr = Array.of_list exprs in
  let len = Array.length arr in
  let result = ref VUnit in
  let pc = ref 0 in
  while !pc < len do
    (try
      result := eval env arr.(!pc);
      pc := !pc + 1
    with GotoLabel target ->
      (* Find label in the expression list *)
      let found = ref false in
      for i = 0 to len - 1 do
        match arr.(i) with
        | Label name when name = target ->
            pc := i + 1;
            found := true
        | _ -> ()
      done;
      if not !found then
        raise (RuntimeError ("Label not found: " ^ target)))
  done;
  !result

and invoke_callable env callable args caller =
  (* Invoke either a VFunction (named) or VClosure (anonymous lambda). *)
  match callable with
  | VFunction (_name, params, _ret_type, body) ->
      let n_expected = List.length params in
      let n_given = List.length args in
      if n_given <> n_expected then
        raise (RuntimeError (caller ^ ": function expects " ^ string_of_int n_expected ^ " args, got " ^ string_of_int n_given));
      let func_env = env_create () in
      Hashtbl.iter (fun k v -> match v with VFunction _ -> env_set func_env k v | _ -> ()) env;
      List.iter2 (fun param a -> env_set func_env param.param_name a) params args;
      (try eval_block func_env body with Return v -> v)
  | VClosure (params, body, snapshot) ->
      let n_expected = List.length params in
      let n_given = List.length args in
      (* Auto-destructuring: when an N-param lambda is invoked with exactly
         one VArray of length N, bind each element to its corresponding
         parameter. Lets `(\(k v) ...)` work on `(entries m)` pairs. *)
      let final_args =
        if n_given = 1 && n_expected >= 2 then
          match args with
          | [VArray arr] when Array.length !arr = n_expected ->
              Array.to_list !arr
          | _ -> args
        else args
      in
      let n_final = List.length final_args in
      if n_final <> n_expected then
        raise (RuntimeError (caller ^ ": closure expects " ^ string_of_int n_expected ^ " args, got " ^ string_of_int n_given));
      let func_env = env_create () in
      Hashtbl.iter (fun k v -> match v with VFunction _ -> env_set func_env k v | _ -> ()) env;
      List.iter (fun (k, v) -> env_set func_env k v) snapshot;
      List.iter2 (fun pname a -> env_set func_env pname a) params final_args;
      (try eval_block func_env body with Return v -> v)
  | VBuiltin name ->
      (* Reference to a builtin — bind args to temporary names, then
         re-dispatch through eval_call. *)
      let tmp_env = env_create () in
      Hashtbl.iter (fun k v -> env_set tmp_env k v) env;
      let tmp_names = List.mapi (fun i _ -> "__hof_arg_" ^ string_of_int i) args in
      List.iter2 (fun n v -> env_set tmp_env n v) tmp_names args;
      let var_args = List.map (fun n -> Var n) tmp_names in
      eval_call tmp_env name var_args
  | _ ->
      raise (RuntimeError (caller ^ ": expected function or closure, got " ^ string_of_value_type callable))

and eval_call env func_name args =
  let arg_vals = List.map (eval env) args in

  (* Alias normalization — accept common Lisp/Clojure/Python synonyms so
     models don't need to memorize Sigil-specific names. Canonical names are
     what the rest of the interpreter implements; aliases map to them here. *)
  let func_name = match func_name with
    | "map"      -> "map_arr"      (* Clojure/Python *)
    | "head"     -> "first"        (* Haskell *)
    | "car"      -> "first"        (* Lisp *)
    | "tail"     -> "rest"         (* Haskell *)
    | "cdr"      -> "rest"         (* Lisp *)
    | "string_length" -> "len"     (* Python str-len reach *)
    | "contains" -> "has"          (* Python 'x in y' semantics *)
    | "size"     -> "len"          (* Ruby/JS *)
    | "length"   -> "len"
    | "count_el" -> "count"        (* disambiguate *)
    | "concat"   -> "add"          (* string/array concatenation *)
    | "upcase"   -> "upper"        (* Ruby *)
    | "downcase" -> "lower"        (* Ruby *)
    | "swap"     -> "swapcase"
    | "abs_val"  -> "abs"
    | "keys"     -> "map_keys"     (* Python/Ruby/JS *)
    | "values"   -> "map_values"   (* Python/Ruby/JS *)
    (* Bit-op aliases — covers names the model reaches for *)
    | "band" | "bitand" | "bit_and_op" -> "bit_and"
    | "bor"  | "bitor"  | "bit_or_op"  -> "bit_or"
    | "bxor" | "bitxor" | "xor" | "bit_xor_op" -> "bit_xor"
    | "bnot" | "bitnot" -> "bit_not"
    | "shl"  | "lsh" | "lshift" | "bit_shl" -> "bit_shift_left"
    | "shr"  | "rsh" | "rshift" | "bit_shr" -> "bit_shift_right"
    (* Arithmetic operator aliases — common in Lisp/Clojure/Scheme *)
    | "+"        -> "add"
    | "-"        -> "sub"
    | "*"        -> "mul"
    | "/"        -> "div"
    | "%"        -> "mod"
    | "<"        -> "lt"
    | ">"        -> "gt"
    | "<="       -> "le"
    | ">="       -> "ge"
    | "="        -> "eq"
    | "=="       -> "eq"
    | "!="       -> "ne"
    | n -> n
  in

  match func_name with
  (* Arithmetic / concat — N-ary, dispatches on first arg type.
     - int/float/decimal: sum
     - string: concat (each arg coerced)
     - array: concatenate elements
     - map: shallow merge (later wins) *)
   | "add" ->
       let coerce_str v = match v with
         | VInt n -> Int64.to_string n
         | VFloat f -> format_float_string f
         | VBool b -> if b then "true" else "false"
         | VDecimal s -> s
         | VString s -> s
         | other -> string_of_value other
       in
       (match arg_vals with
        | [] -> raise (RuntimeError "add: requires at least 2 arguments")
        | [_] -> raise (RuntimeError "add: requires at least 2 arguments")
        | first :: _ ->
            (match first with
             | VInt _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VInt a, VInt b -> VInt (Int64.add a b)
                   | VInt a, VFloat b -> VFloat (Int64.to_float a +. b)
                   | VFloat a, VInt b -> VFloat (a +. Int64.to_float b)
                   | VFloat a, VFloat b -> VFloat (a +. b)
                   | _ -> raise (RuntimeError "add: numeric/numeric expected"))
                   first (List.tl arg_vals)
             | VFloat _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VFloat a, VFloat b -> VFloat (a +. b)
                   | VFloat a, VInt b -> VFloat (a +. Int64.to_float b)
                   | VInt a, VFloat b -> VFloat (Int64.to_float a +. b)
                   | _ -> raise (RuntimeError "add: numeric/numeric expected"))
                   first (List.tl arg_vals)
             | VDecimal _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VDecimal a, VDecimal b -> VDecimal (bigdecimal_add a b)
                   | _ -> raise (RuntimeError "add: decimal/decimal expected"))
                   first (List.tl arg_vals)
             | VString _ ->
                 (* Any-typed string concat: coerce non-string args. *)
                 VString (String.concat "" (List.map coerce_str arg_vals))
             | VArray _ ->
                 let buf = ref [||] in
                 List.iter (fun v -> match v with
                   | VArray a -> buf := Array.append !buf !a
                   | other -> buf := Array.append !buf [|other|]
                 ) arg_vals;
                 VArray (ref !buf)
             | VMap _ ->
                 (* Shallow merge; later values win on collision. Insertion order
                    preserved: keys from the first map come first, then any new
                    keys from later maps in order. *)
                 let merged = Hashtbl.create 16 in
                 let order = ref [] in
                 List.iter (fun v -> match v with
                   | VMap (m, keys) ->
                       List.iter (fun k ->
                         if not (Hashtbl.mem merged k) then order := k :: !order;
                         Hashtbl.replace merged k (Hashtbl.find m k)
                       ) !keys
                   | _ -> raise (RuntimeError "add: cannot mix map with non-map")
                 ) arg_vals;
                 VMap (merged, ref (List.rev !order))
             | _ -> raise (RuntimeError "Invalid arguments to add")))

   | "sub" ->
       (* Variadic left-fold like add: `(- a b c d)` = a - b - c - d.
          Unary form `(- x)` = negation (standard Lisp/Scheme convention).
          Models writing `(sub len_a i 1)` expecting "len_a - i - 1" used
          to crash with an arity error — now it works. *)
       (match arg_vals with
        | [] -> raise (RuntimeError "sub: requires at least 1 argument")
        | [VInt a] -> VInt (Int64.neg a)
        | [VFloat a] -> VFloat (-. a)
        | [VDecimal a] -> VDecimal (bigdecimal_neg a)
        | [_] -> raise (RuntimeError
            ("sub: unary negation requires int/float/decimal, got "
             ^ fmt_arg_types arg_vals))
        | first :: _ ->
            (match first with
             | VInt _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VInt a, VInt b -> VInt (Int64.sub a b)
                   | VInt a, VFloat b -> VFloat (Int64.to_float a -. b)
                   | VFloat a, VInt b -> VFloat (a -. Int64.to_float b)
                   | VFloat a, VFloat b -> VFloat (a -. b)
                   | _ -> raise (RuntimeError
                       ("sub: numeric/numeric expected, got "
                        ^ fmt_arg_types arg_vals)))
                   first (List.tl arg_vals)
             | VFloat _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VFloat a, VFloat b -> VFloat (a -. b)
                   | VFloat a, VInt b -> VFloat (a -. Int64.to_float b)
                   | VInt a, VFloat b -> VFloat (Int64.to_float a -. b)
                   | _ -> raise (RuntimeError
                       ("sub: numeric/numeric expected, got "
                        ^ fmt_arg_types arg_vals)))
                   first (List.tl arg_vals)
             | VDecimal _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VDecimal a, VDecimal b -> VDecimal (bigdecimal_sub a b)
                   | _ -> raise (RuntimeError
                       ("sub: decimal/decimal expected, got "
                        ^ fmt_arg_types arg_vals)))
                   first (List.tl arg_vals)
             | _ -> raise (RuntimeError
                 ("sub: numeric expected, got " ^ fmt_arg_types arg_vals))))

   | "mul" ->
       (* Variadic left-fold like add/sub: a*b*c... *)
       (match arg_vals with
        | [] | [_] -> raise (RuntimeError
            ("mul: requires at least 2 arguments, got " ^ fmt_arg_types arg_vals))
        | [VString s; VInt n] | [VInt n; VString s] ->
            let n = Int64.to_int n in
            if n <= 0 then VString ""
            else VString (String.concat "" (List.init n (fun _ -> s)))
        | first :: _ ->
            (match first with
             | VInt _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VInt a, VInt b -> VInt (Int64.mul a b)
                   | VInt a, VFloat b -> VFloat (Int64.to_float a *. b)
                   | VFloat a, VInt b -> VFloat (a *. Int64.to_float b)
                   | VFloat a, VFloat b -> VFloat (a *. b)
                   | _ -> raise (RuntimeError
                       ("mul: numeric/numeric expected, got "
                        ^ fmt_arg_types arg_vals)))
                   first (List.tl arg_vals)
             | VFloat _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VFloat a, VFloat b -> VFloat (a *. b)
                   | VFloat a, VInt b -> VFloat (a *. Int64.to_float b)
                   | VInt a, VFloat b -> VFloat (Int64.to_float a *. b)
                   | _ -> raise (RuntimeError
                       ("mul: numeric/numeric expected, got "
                        ^ fmt_arg_types arg_vals)))
                   first (List.tl arg_vals)
             | VDecimal _ ->
                 List.fold_left (fun acc v -> match acc, v with
                   | VDecimal a, VDecimal b -> VDecimal (bigdecimal_mul a b)
                   | _ -> raise (RuntimeError
                       ("mul: decimal/decimal expected, got "
                        ^ fmt_arg_types arg_vals)))
                   first (List.tl arg_vals)
             | _ -> raise (RuntimeError
                 ("mul: numeric expected, got " ^ fmt_arg_types arg_vals))))

   | "div" ->
       (match arg_vals with
        | [VInt a; VInt b] ->
            if b = 0L then raise (RuntimeError "Division by zero")
            else VInt (Int64.div a b)
         | [VFloat a; VFloat b] ->
             if b = 0.0 then raise (RuntimeError "Division by zero")
             else VFloat (a /. b)
        | [VDecimal a; VDecimal b] ->
             VDecimal (bigdecimal_div a b ~precision:20 ())
         | _ -> raise (RuntimeError
             ("div takes (int int), (float float), or (decimal decimal); got "
              ^ fmt_arg_types arg_vals)))

  | "mod" ->
      (match arg_vals with
       | [VInt a; VInt b] ->
           if b = 0L then raise (RuntimeError "Division by zero")
           else VInt (Int64.rem a b)
       | _ -> raise (RuntimeError
           ("mod takes (int int), got " ^ fmt_arg_types arg_vals)))
  
   (* Bitwise operations - int only *)
   | "bit_and" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.logand a b)
        | _ -> raise (RuntimeError "Invalid arguments to bit_and"))

   | "bit_or" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.logor a b)
        | _ -> raise (RuntimeError "Invalid arguments to bit_or"))

   | "bit_xor" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.logxor a b)
        | _ -> raise (RuntimeError "Invalid arguments to bit_xor"))

   | "bit_not" ->
       (match arg_vals with
        | [VInt a] -> VInt (Int64.lognot a)
        | _ -> raise (RuntimeError "Invalid arguments to bit_not"))

   | "bit_shift_left" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.shift_left a (Int64.to_int b))
        | _ -> raise (RuntimeError "Invalid arguments to bit_shift_left"))

   | "bit_shift_right" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.shift_right_logical a (Int64.to_int b))
        | _ -> raise (RuntimeError "Invalid arguments to bit_shift_right"))

   | "neg" ->
       (match arg_vals with
        | [VInt a] -> VInt (Int64.neg a)
        | [VFloat a] -> VFloat (a *. -1.0)
        | [VDecimal a] ->
             VDecimal (bigdecimal_neg a)
         | _ -> raise (RuntimeError "Invalid arguments to neg"))

  | "abs" ->
      (match arg_vals with
       | [VInt a] -> VInt (if a < 0L then Int64.neg a else a)
       | [VFloat a] -> VFloat (abs_float a)
       | [VDecimal a] ->
            VDecimal (bigdecimal_abs a)
       | _ -> raise (RuntimeError
           ("abs takes (int), (float), or (decimal); got " ^ fmt_arg_types arg_vals)))

  | "min" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VInt (if a < b then a else b)
       | [VFloat a; VFloat b] -> VFloat (min a b)
       | [VDecimal a; VDecimal b] ->
            if bigdecimal_compare a b <= 0 then VDecimal (decimal_normalize a) else VDecimal (decimal_normalize b)
       | _ -> raise (RuntimeError
           ("min takes (int int), (float float), or (decimal decimal); for arrays use min_of; got "
            ^ fmt_arg_types arg_vals)))

  | "max" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VInt (if a > b then a else b)
       | [VFloat a; VFloat b] -> VFloat (max a b)
       | [VDecimal a; VDecimal b] ->
            if bigdecimal_compare a b >= 0 then VDecimal (decimal_normalize a) else VDecimal (decimal_normalize b)
       | _ -> raise (RuntimeError
           ("max takes (int int), (float float), or (decimal decimal); for arrays use max_of; got "
            ^ fmt_arg_types arg_vals)))

  | "sqrt" ->
      (match arg_vals with
       | [VFloat a] -> VFloat (sqrt a)
       | [VInt a] -> VFloat (sqrt (Int64.to_float a))
       | _ -> raise (RuntimeError "sqrt takes (int) or (float)"))

   | "pow" ->
      (* Polymorphic on int/float to match what models reach for: (pow 2 16),
         (pow 2.0 0.5). Returns int when both args are int, else float. *)
      (match arg_vals with
       | [VInt a; VInt b] ->
           let bf = Int64.to_int b in
           if bf < 0 then VFloat ((Int64.to_float a) ** (Int64.to_float b))
           else
             let rec ipow base exp acc =
               if exp = 0 then acc
               else if exp mod 2 = 1 then ipow (Int64.mul base base) (exp / 2) (Int64.mul acc base)
               else ipow (Int64.mul base base) (exp / 2) acc
             in VInt (ipow a bf 1L)
       | [VFloat a; VFloat b] -> VFloat (a ** b)
       | [VInt a; VFloat b] -> VFloat ((Int64.to_float a) ** b)
       | [VFloat a; VInt b] -> VFloat (a ** (Int64.to_float b))
       | _ -> raise (RuntimeError "pow takes (int, int) or (float, float)"))

  | "floor" ->
      (match arg_vals with
       | [VFloat f] -> VInt (Int64.of_float (floor f))
       | _ -> raise (RuntimeError "Invalid arguments to floor: expects (float) -> int"))

  | "ceil" ->
      (match arg_vals with
       | [VFloat f] -> VInt (Int64.of_float (ceil f))
       | _ -> raise (RuntimeError "Invalid arguments to ceil: expects (float) -> int"))

  | "round" ->
      (match arg_vals with
       | [VFloat f] -> VInt (Int64.of_float (Float.round f))
       | _ -> raise (RuntimeError "Invalid arguments to round: expects (float) -> int"))

  (* Comparisons *)
   | "eq" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VBool (a = b)
        | [VFloat a; VFloat b] -> VBool (a = b)
        | [VBool a; VBool b] -> VBool (a = b)
        | [VString a; VString b] -> VBool (a = b)
         | [VDecimal a; VDecimal b] ->
              VBool (bigdecimal_compare a b = 0)
          | [VArray _ as a; VArray _ as b] -> VBool (values_equal a b)
         | [VMap _ as a; VMap _ as b] -> VBool (values_equal a b)
         | [a; b] -> raise (RuntimeError ("eq requires arguments of the same type, got " ^ string_of_value_type a ^ " and " ^ string_of_value_type b))
         | _ -> raise (RuntimeError
             ("eq takes 2 args of the same type, got " ^ fmt_arg_types arg_vals)))
  
   | "ne" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VBool (a <> b)
        | [VFloat a; VFloat b] -> VBool (a <> b)
        | [VBool a; VBool b] -> VBool (a <> b)
        | [VString a; VString b] -> VBool (a <> b)
         | [VDecimal a; VDecimal b] ->
             VBool (bigdecimal_compare a b <> 0)
         | [VArray _ as a; VArray _ as b] -> VBool (not (values_equal a b))
         | [VMap _ as a; VMap _ as b] -> VBool (not (values_equal a b))
         | [a; b] -> raise (RuntimeError ("ne requires arguments of the same type, got " ^ string_of_value_type a ^ " and " ^ string_of_value_type b))
         | _ -> raise (RuntimeError
             ("ne takes 2 args of the same type, got " ^ fmt_arg_types arg_vals)))
  
  | "lt" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a < b)
       | [VFloat a; VFloat b] -> VBool (a < b)
       | [VString a; VString b] -> VBool (a < b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b < 0)
       | _ -> raise (RuntimeError
           ("lt takes 2 numeric or 2 string args, got " ^ fmt_arg_types arg_vals)))

  | "gt" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a > b)
       | [VFloat a; VFloat b] -> VBool (a > b)
       | [VString a; VString b] -> VBool (a > b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b > 0)
       | _ -> raise (RuntimeError
           ("gt takes 2 numeric or 2 string args, got " ^ fmt_arg_types arg_vals)))

  | "le" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a <= b)
       | [VFloat a; VFloat b] -> VBool (a <= b)
       | [VString a; VString b] -> VBool (a <= b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b <= 0)
       | _ -> raise (RuntimeError
           ("le takes 2 numeric or 2 string args, got " ^ fmt_arg_types arg_vals)))

  | "ge" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a >= b)
       | [VFloat a; VFloat b] -> VBool (a >= b)
       | [VString a; VString b] -> VBool (a >= b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b >= 0)
       | _ -> raise (RuntimeError
           ("ge takes 2 numeric or 2 string args, got " ^ fmt_arg_types arg_vals)))

  (* Logical operations *)
  | "not" ->
      (match arg_vals with
       | [VBool a] -> VBool (not a)
       | _ -> raise (RuntimeError
           ("not takes 1 bool, got " ^ fmt_arg_types arg_vals)))

  (* Type conversions *)
  | "cast_int_float" ->
      (match arg_vals with
       | [VInt a] -> VFloat (Int64.to_float a)
       | _ -> raise (RuntimeError "Invalid arguments to cast_int_float"))

   | "cast_float_int" ->
       (match arg_vals with
        | [VFloat a] -> VInt (Int64.of_float a)
        | _ -> raise (RuntimeError "Invalid arguments to cast_float_int"))

   | "cast_int_decimal" ->
       (match arg_vals with
        | [VInt a] -> VDecimal (Int64.to_string a)
        | _ -> raise (RuntimeError "Invalid arguments to cast_int_decimal"))

    | "cast_decimal_int" ->
        (match arg_vals with
         | [VDecimal s] ->
             (* Handle fractional decimals by truncating toward zero *)
             let (neg, int_part, _) = decimal_parse s in
             let int_part = strip_leading_zeros int_part in
             let n = Int64.of_string int_part in
             if neg then VInt (Int64.neg n) else VInt n
         | _ -> raise (RuntimeError "Invalid arguments to cast_decimal_int: expected decimal"))

   | "string_from_int" ->
      (match arg_vals with
       | [VInt a] -> VString (Int64.to_string a)
       | _ -> raise (RuntimeError "Invalid arguments to string_from_int"))

   | "string_to_int" ->
      (match arg_vals with
       | [VString s] ->
           (try VInt (Int64.of_string (String.trim s))
            with Failure _ -> raise (RuntimeError ("Cannot convert to int: " ^ s)))
       | _ -> raise (RuntimeError "Invalid arguments to string_to_int"))

  | "string_from_float" ->
      (match arg_vals with
       | [VFloat a] -> VString (format_float_string a)
       | _ -> raise (RuntimeError "Invalid arguments to string_from_float"))

  | "string_to_float" ->
      (match arg_vals with
       | [VString s] ->
           (try VFloat (float_of_string (String.trim s))
            with Failure _ -> raise (RuntimeError ("Cannot convert to float: " ^ s)))
       | _ -> raise (RuntimeError "Invalid arguments to string_to_float"))

  | "string_from_bool" ->
      (match arg_vals with
       | [VBool a] -> VString (string_of_bool a)
       | _ -> raise (RuntimeError "Invalid arguments to string_from_bool"))

  (* String operations *)
   | "string_length" ->
       (match arg_vals with
        | [VString s] -> VInt (Int64.of_int (String.length s))
        | _ -> raise (RuntimeError "Invalid arguments to string_length: expected string"))

  | "string_concat" ->
      (match arg_vals with
       | [VString a; VString b] -> VString (a ^ b)
       | _ -> raise (RuntimeError "Invalid arguments to string_concat"))

  | "string_equals" ->
      (match arg_vals with
       | [VString a; VString b] -> VBool (a = b)
       | _ -> raise (RuntimeError "Invalid arguments to string_equals"))

  | "string_slice" ->
      (match arg_vals with
       | [VString s; VInt start; VInt len] ->
           let s_len = String.length s in
           let s_i = Int64.to_int start in
           let s_len' = Int64.to_int len in
           if s_i >= 0 && s_i + s_len' <= s_len then
             VString (String.sub s s_i s_len')
           else if s_i < s_len then
             VString (String.sub s s_i (s_len - s_i))
           else
             VString ""
       | _ -> raise (RuntimeError "Invalid arguments to string_slice"))

    | "string_get" ->
       (match arg_vals with
        | [VString s; VInt idx] ->
            let i = Int64.to_int idx in
            if i >= 0 && i < String.length s then
              VInt (Int64.of_int (Char.code s.[i]))
            else
              raise (RuntimeError ("String index out of bounds: " ^ Int64.to_string idx))
        | _ -> raise (RuntimeError "Invalid arguments to string_get"))

   | "string_format" ->
       (match arg_vals with
        | VString template :: format_args ->
            let buf = Buffer.create (String.length template) in
            let len = String.length template in
            let arg_idx = ref 0 in
            let i = ref 0 in
            while !i < len do
              if !i + 1 < len && template.[!i] = '{' && template.[!i + 1] = '}' then begin
                if !arg_idx < List.length format_args then begin
                  Buffer.add_string buf (string_of_value (List.nth format_args !arg_idx));
                  arg_idx := !arg_idx + 1
                end else
                  Buffer.add_string buf "{}";
                i := !i + 2
              end else begin
                Buffer.add_char buf template.[!i];
                i := !i + 1
              end
            done;
            VString (Buffer.contents buf)
        | _ -> raise (RuntimeError "string_format requires a template string"))

   | "string_find" ->
       (match arg_vals with
        | [VString haystack; VString needle] ->
            let h_len = String.length haystack in
            let n_len = String.length needle in
            if n_len = 0 then VInt 0L
            else if n_len > h_len then VInt (-1L)
            else begin
              let found = ref (-1) in
              let i = ref 0 in
              while !i <= h_len - n_len && !found = -1 do
                if String.sub haystack !i n_len = needle then
                  found := !i
                else
                  i := !i + 1
              done;
              VInt (Int64.of_int !found)
            end
        | _ -> raise (RuntimeError "Invalid arguments to string_find"))

   | "string_to_upper" ->
       (match arg_vals with
        | [VString s] -> VString (String.uppercase_ascii s)
        | _ -> raise (RuntimeError "Invalid arguments to string_to_upper"))

   | "string_to_lower" ->
       (match arg_vals with
        | [VString s] -> VString (String.lowercase_ascii s)
        | _ -> raise (RuntimeError "Invalid arguments to string_to_lower"))

   | "string_split" ->
       (match arg_vals with
        | [VString s; VString delim] ->
            if String.length delim = 0 then
              VArray (ref (Array.of_list (List.map (fun c -> VString (String.make 1 c)) (List.of_seq (String.to_seq s)))))
            else
              let parts = String.split_on_char delim.[0] s in
              if String.length delim = 1 then
                VArray (ref (Array.of_list (List.map (fun p -> VString p) parts)))
              else begin
                let results = ref [] in
                let remaining = ref s in
                let dlen = String.length delim in
                let continue_loop = ref true in
                while !continue_loop do
                  match String.split_on_char delim.[0] !remaining with
                  | [] -> continue_loop := false
                  | _ ->
                    let pos = ref (-1) in
                    let rlen = String.length !remaining in
                    let i = ref 0 in
                    while !i <= rlen - dlen && !pos = -1 do
                      if String.sub !remaining !i dlen = delim then
                        pos := !i
                      else
                        i := !i + 1
                    done;
                    if !pos = -1 then begin
                      results := VString !remaining :: !results;
                      continue_loop := false
                    end else begin
                      results := VString (String.sub !remaining 0 !pos) :: !results;
                      remaining := String.sub !remaining (!pos + dlen) (rlen - !pos - dlen)
                    end
                done;
                VArray (ref (Array.of_list (List.rev !results)))
              end
        | _ -> raise (RuntimeError "Invalid arguments to string_split"))

   | "string_join" ->
       (match arg_vals with
        | [VArray arr; VString delim] ->
            let parts = Array.to_list !arr |> List.map (fun v ->
              match v with
              | VString s -> s
              | VInt n -> Int64.to_string n
              | VFloat f -> string_of_float f
              | VBool b -> string_of_bool b
              | _ -> raise (RuntimeError "string_join: array contains non-stringifiable value")
            ) in
            VString (String.concat delim parts)
         | _ -> raise (RuntimeError "Invalid arguments to string_join"))

   | "string_starts_with" ->
       (match arg_vals with
        | [VString s; VString prefix] ->
            let plen = String.length prefix in
            VBool (String.length s >= plen && String.sub s 0 plen = prefix)
        | _ -> raise (RuntimeError "Invalid arguments to string_starts_with: expects (string, string) -> bool"))

   | "string_ends_with" ->
       (match arg_vals with
        | [VString s; VString suffix] ->
            let slen = String.length s in
            let xlen = String.length suffix in
            VBool (slen >= xlen && String.sub s (slen - xlen) xlen = suffix)
        | _ -> raise (RuntimeError "Invalid arguments to string_ends_with: expects (string, string) -> bool"))

   | "string_contains" ->
       (match arg_vals with
        | [VString haystack; VString needle] ->
            let hlen = String.length haystack in
            let nlen = String.length needle in
            if nlen = 0 then VBool true
            else if nlen > hlen then VBool false
            else begin
              let found = ref false in
              let i = ref 0 in
              while !i <= hlen - nlen && not !found do
                if String.sub haystack !i nlen = needle then
                  found := true
                else
                  i := !i + 1
              done;
              VBool !found
            end
        | _ -> raise (RuntimeError "Invalid arguments to string_contains: expects (string, string) -> bool"))

   | "in" ->
       (match arg_vals with
        | [VString needle; VString haystack] ->
            let hlen = String.length haystack in
            let nlen = String.length needle in
            if nlen = 0 then VBool true
            else if nlen > hlen then VBool false
            else begin
              let found = ref false in
              let i = ref 0 in
              while not !found && !i <= hlen - nlen do
                if String.sub haystack !i nlen = needle then found := true
                else i := !i + 1
              done;
              VBool !found
            end
        | [v; VArray arr] ->
            VBool (Array.exists (fun x -> values_equal x v) !arr)
        | [VString key; VMap (m, _)] ->
            VBool (Hashtbl.mem m key)
        | _ -> raise (RuntimeError "in: expects (string, string) for substring, (value, array) for element, or (key, map)"))

   | "has" ->
       (* Reverse-arg synonym for `in`: (has coll x) == (in x coll).
          Models often reach for "collection.has(x)" shape. *)
       (match arg_vals with
        | [VString haystack; VString needle] ->
            let hlen = String.length haystack in
            let nlen = String.length needle in
            if nlen = 0 then VBool true
            else if nlen > hlen then VBool false
            else begin
              let found = ref false in
              let i = ref 0 in
              while not !found && !i <= hlen - nlen do
                if String.sub haystack !i nlen = needle then found := true
                else i := !i + 1
              done;
              VBool !found
            end
        | [VArray arr; v] ->
            VBool (Array.exists (fun x -> values_equal x v) !arr)
        | [VMap (m, _); VString key] ->
            VBool (Hashtbl.mem m key)
        | _ -> raise (RuntimeError "has: expects (coll, element) — reverse of `in`"))

   | "string_trim" ->
       (match arg_vals with
        | [VString s] ->
            let len = String.length s in
            let i = ref 0 in
            while !i < len && (s.[!i] = ' ' || s.[!i] = '\t' || s.[!i] = '\n' || s.[!i] = '\r') do
              i := !i + 1
            done;
            let j = ref (len - 1) in
            while !j >= !i && (s.[!j] = ' ' || s.[!j] = '\t' || s.[!j] = '\n' || s.[!j] = '\r') do
              j := !j - 1
            done;
            if !i > !j then VString ""
            else VString (String.sub s !i (!j - !i + 1))
        | _ -> raise (RuntimeError "Invalid arguments to string_trim: expects (string) -> string"))

   | "string_replace" ->
       (match arg_vals with
        | [VString s; VString old_s; VString new_s] ->
            let olen = String.length old_s in
            if olen = 0 then VString s
            else begin
              let buf = Buffer.create (String.length s) in
              let slen = String.length s in
              let i = ref 0 in
              while !i < slen do
                if !i <= slen - olen && String.sub s !i olen = old_s then begin
                  Buffer.add_string buf new_s;
                  i := !i + olen
                end else begin
                  Buffer.add_char buf s.[!i];
                  i := !i + 1
                end
              done;
              VString (Buffer.contents buf)
            end
        | _ -> raise (RuntimeError "Invalid arguments to string_replace: expects (string, string, string) -> string"))

  (* Array operations *)
  | "array_new" ->
      VArray (ref [||])
  
  | "array_push" ->
      (match arg_vals with
       | [VArray arr; v] ->
           let new_arr = Array.append !arr (Array.make 1 v) in
           arr := new_arr;
           VArray arr
       | _ -> raise (RuntimeError "Invalid arguments to array_push"))

  | "array_get" ->
      (match arg_vals with
       | [VArray arr; VInt idx] ->
           let n = Array.length !arr in
           let i = Int64.to_int idx in
           let actual = if i < 0 then n + i else i in  (* negative indexing from end *)
           if actual >= 0 && actual < n then
             !arr.(actual)
           else
             raise (RuntimeError ("Array index out of bounds: " ^ Int64.to_string idx))
       | _ -> raise (RuntimeError "Invalid arguments to array_get"))

  (* Polymorphic strict access — same concept across collection types:
     "give me the element at this position/key, raise if absent."
     - get_or stays the explicit safe form (default on miss)
     - json_get stays the explicit deep-traversal form
     This fills the same-concept gap matching Clojure/Python `dict[k]`. *)
  | "get" ->
      (match arg_vals with
       | [VArray arr; VInt idx] ->
           let n = Array.length !arr in
           let i = Int64.to_int idx in
           let actual = if i < 0 then n + i else i in
           if actual >= 0 && actual < n then !arr.(actual)
           else raise (RuntimeError ("get: array index out of bounds: " ^ Int64.to_string idx))
       | [VString s; VInt idx] ->
           let n = String.length s in
           let i = Int64.to_int idx in
           let actual = if i < 0 then n + i else i in
           if actual >= 0 && actual < n then VString (String.make 1 s.[actual])
           else raise (RuntimeError ("get: string index out of bounds: " ^ Int64.to_string idx))
       | [VMap (m, _); VString k] ->
           (try Hashtbl.find m k
            with Not_found -> raise (RuntimeError ("get: key not found in map: " ^ k)))
       | _ -> raise (RuntimeError "get takes (array|string, int) or (map, string) — for JSON deep traversal use json_get; for default-on-miss use get_or"))

  | "first" ->
      (match arg_vals with
       | [VArray arr] ->
           if Array.length !arr = 0 then
             raise (RuntimeError "first: empty array")
           else !arr.(0)
       | [VString s] ->
           if String.length s = 0 then
             raise (RuntimeError "first: empty string")
           else VString (String.make 1 s.[0])
       | _ -> raise (RuntimeError "first takes (array) or (string)"))

  | "second" ->
      (* Common LLM reach (Clojure/Lisp); equivalent to (get x 1). Returns the
         second element of an array or 1-char string at index 1. *)
      (match arg_vals with
       | [VArray arr] ->
           if Array.length !arr < 2 then
             raise (RuntimeError "second: array has fewer than 2 elements")
           else !arr.(1)
       | [VString s] ->
           if String.length s < 2 then
             raise (RuntimeError "second: string has fewer than 2 characters")
           else VString (String.make 1 s.[1])
       | _ -> raise (RuntimeError "second takes (array) or (string)"))

  | "third" ->
      (* Common LLM reach (Clojure/Lisp); equivalent to (get x 2). *)
      (match arg_vals with
       | [VArray arr] ->
           if Array.length !arr < 3 then
             raise (RuntimeError "third: array has fewer than 3 elements")
           else !arr.(2)
       | [VString s] ->
           if String.length s < 3 then
             raise (RuntimeError "third: string has fewer than 3 characters")
           else VString (String.make 1 s.[2])
       | _ -> raise (RuntimeError "third takes (array) or (string)"))

  | "last" ->
      (match arg_vals with
       | [VArray arr] ->
           let n = Array.length !arr in
           if n = 0 then
             raise (RuntimeError "last: empty array")
           else !arr.(n - 1)
       | [VString s] ->
           let n = String.length s in
           if n = 0 then
             raise (RuntimeError "last: empty string")
           else VString (String.make 1 s.[n - 1])
       | _ -> raise (RuntimeError "last takes (array) or (string)"))

  | "rest" ->
      (* Haskell/Lisp tail: everything except the first element.
         Empty input returns empty. *)
      (match arg_vals with
       | [VArray arr] ->
           let n = Array.length !arr in
           if n <= 1 then VArray (ref [||])
           else VArray (ref (Array.sub !arr 1 (n - 1)))
       | [VString s] ->
           let n = String.length s in
           if n <= 1 then VString ""
           else VString (String.sub s 1 (n - 1))
       | _ -> raise (RuntimeError "rest takes (array) or (string)"))

  | "array_set" ->
      (match arg_vals with
       | [VArray arr; VInt idx; v] ->
           let i = Int64.to_int idx in
           if i >= 0 && i < Array.length !arr then
             (!arr).(i) <- v
           else
             raise (RuntimeError ("Array index out of bounds: " ^ Int64.to_string idx));
           VArray arr
       | _ -> raise (RuntimeError "Invalid arguments to array_set"))

   | "array_length" ->
       (match arg_vals with
        | [VArray arr] -> VInt (Int64.of_int (Array.length !arr))
        | _ -> raise (RuntimeError "Invalid arguments to array_length"))

   | "array_copy" ->
       (match arg_vals with
        | [VArray _ as v] -> deep_copy_value v
        | _ -> raise (RuntimeError "Invalid arguments to array_copy"))

   | "array_sort" ->
       (match arg_vals with
        | [VArray arr] ->
            let compare_values a b =
              match a, b with
              | VInt x, VInt y -> Int64.compare x y
              | VFloat x, VFloat y -> compare x y
              | VString x, VString y -> String.compare x y
              | VDecimal x, VDecimal y -> bigdecimal_compare x y
              | VBool x, VBool y -> compare x y
              | _ -> raise (RuntimeError "array_sort: cannot compare mixed types")
            in
            let sorted = Array.copy !arr in
            Array.sort compare_values sorted;
            arr := sorted;
            VArray arr
        | _ -> raise (RuntimeError "Invalid arguments to array_sort"))

   | "array_reverse" | "rev" ->
       (match arg_vals with
        | [VArray arr] ->
            let len = Array.length !arr in
            let reversed = Array.init len (fun i -> !arr.(len - 1 - i)) in
            arr := reversed;
            VArray arr
        | [VString s] ->
            let len = String.length s in
            let buf = Bytes.create len in
            for i = 0 to len - 1 do
              Bytes.set buf i s.[len - 1 - i]
            done;
            VString (Bytes.to_string buf)
        | _ -> raise (RuntimeError "rev takes array or string"))

   | "array_contains" ->
       (match arg_vals with
        | [VArray arr; v] ->
            VBool (Array.exists (fun elem -> values_equal elem v) !arr)
        | _ -> raise (RuntimeError "Invalid arguments to array_contains"))

   | "array_index_of" ->
       (match arg_vals with
        | [VArray arr; v] ->
            let len = Array.length !arr in
            let found = ref (-1) in
            let i = ref 0 in
            while !i < len && !found = -1 do
              if values_equal !arr.(!i) v then found := !i;
              i := !i + 1
            done;
            VInt (Int64.of_int !found)
        | _ -> raise (RuntimeError "Invalid arguments to array_index_of"))

   (* Polymorphic alias used by most LLMs — dispatches by first arg type *)
   | "index_of" ->
       (match arg_vals with
        | [VString haystack; VString needle] ->
            let h_len = String.length haystack in
            let n_len = String.length needle in
            if n_len = 0 then VInt 0L
            else if n_len > h_len then VInt (-1L)
            else begin
              let found = ref (-1) in
              let i = ref 0 in
              while !i <= h_len - n_len && !found = -1 do
                if String.sub haystack !i n_len = needle then found := !i
                else i := !i + 1
              done;
              VInt (Int64.of_int !found)
            end
        | [VArray arr; v] ->
            let len = Array.length !arr in
            let found = ref (-1) in
            let i = ref 0 in
            while !i < len && !found = -1 do
              if values_equal !arr.(!i) v then found := !i;
              i := !i + 1
            done;
            VInt (Int64.of_int !found)
        | _ -> raise (RuntimeError
            ("index_of takes (string, string) or (array, value), got "
             ^ fmt_arg_types arg_vals)))

   | "pop" ->
       (match arg_vals with
        | [VArray arr] ->
            let n = Array.length !arr in
            if n = 0 then raise (RuntimeError "pop on empty array")
            else begin
              let last = !arr.(n - 1) in
              arr := Array.sub !arr 0 (n - 1);
              last
            end
        | _ -> raise (RuntimeError "pop takes (array)"))

   (* Map operations *)
  | "map_new" ->
      make_vmap ()
  
  | "map_set" ->
      (match arg_vals with
       | [VMap (m, keys); VString k; v] ->
           vmap_set m keys k v;
           VMap (m, keys)
       | _ -> raise (RuntimeError "Invalid arguments to map_set"))

   | "map_get" ->
       (match arg_vals with
        | [VMap (m, _); VString k] ->
            (try Hashtbl.find m k
             with Not_found -> raise (RuntimeError ("Key not found in map: " ^ k)))
        | _ -> raise (RuntimeError "Invalid arguments to map_get"))

  | "map_has" ->
      (match arg_vals with
       | [VMap (m, _); VString k] -> VBool (Hashtbl.mem m k)
       | _ -> raise (RuntimeError "Invalid arguments to map_has"))

  | "map_delete" ->
      (match arg_vals with
       | [VMap (m, keys); VString k] ->
           vmap_delete m keys k;
           VMap (m, keys)
       | _ -> raise (RuntimeError "Invalid arguments to map_delete"))

   | "map_keys" ->
       (match arg_vals with
        | [VMap (_, keys)] ->
            VArray (ref (Array.of_list (List.map (fun k -> VString k) !keys)))
        | _ -> raise (RuntimeError "Invalid arguments to map_keys"))

   | "map_copy" ->
       (match arg_vals with
        | [VMap _ as v] -> deep_copy_value v
        | _ -> raise (RuntimeError "Invalid arguments to map_copy"))

   | "map_entries" ->
       (match arg_vals with
        | [VMap (m, keys)] ->
            let entries = List.map (fun k ->
              let v = Hashtbl.find m k in
              let entry = Hashtbl.create 2 in
              let entry_keys = ref [] in
              vmap_set entry entry_keys "key" (VString k);
              vmap_set entry entry_keys "value" v;
              VMap (entry, entry_keys)
            ) !keys in
            VArray (ref (Array.of_list entries))
        | _ -> raise (RuntimeError "Invalid arguments to map_entries"))

   | "entries" ->
       (* Python .items() style: array of [key, value] pairs. *)
       (match arg_vals with
        | [VMap (m, keys)] ->
            let pairs = List.map (fun k ->
              VArray (ref [| VString k; Hashtbl.find m k |])
            ) !keys in
            VArray (ref (Array.of_list pairs))
        | _ -> raise (RuntimeError "entries takes 1 map"))

   (* Helper: read entire file *)
   | "file_read" ->
       (match arg_vals with
        | [VString path] ->
            try
              let fd = Unix.openfile path [Unix.O_RDONLY] 0o644 in
              let len = Unix.lseek fd 0 Unix.SEEK_END in
              let _ = Unix.lseek fd 0 Unix.SEEK_SET in
              let buf = Bytes.create len in
              let rec read_all offset remaining =
                if remaining <= 0 then ()
                else
                  let n = Unix.read fd buf offset remaining in
                  if n = 0 then ()
                  else read_all (offset + n) (remaining - n)
              in
              read_all 0 len;
              Unix.close fd;
              VString (Bytes.to_string buf)
            with Unix.Unix_error _ ->
              raise (RuntimeError ("Could not read file: " ^ path))
        | _ -> raise (RuntimeError "Invalid arguments to file_read"))

   | "file_write" ->
       (match arg_vals with
        | [VString path; VString content] ->
            try
              let fd = Unix.openfile path [Unix.O_WRONLY; Unix.O_CREAT; Unix.O_TRUNC] 0o644 in
              let _ = Unix.write fd (Bytes.of_string content) 0 (String.length content) in
              Unix.close fd;
              VBool true
            with Unix.Unix_error _ ->
              raise (RuntimeError ("Could not write file: " ^ path))
        | _ -> raise (RuntimeError "Invalid arguments to file_write"))

   | "file_exists" ->
       (match arg_vals with
        | [VString path] -> VBool (Sys.file_exists path)
        | _ -> raise (RuntimeError "Invalid arguments to file_exists"))

   | "file_size" ->
       (match arg_vals with
        | [VString path] ->
            (try
              let stats = Unix.stat path in
              VInt (Int64.of_int stats.Unix.st_size)
            with Unix.Unix_error _ ->
              raise (RuntimeError ("Could not stat file: " ^ path)))
        | _ -> raise (RuntimeError "Invalid arguments to file_size"))

   | "file_delete" ->
       (match arg_vals with
        | [VString path] ->
            try
              Unix.unlink path;
              VBool true
            with Unix.Unix_error _ ->
              VBool false
         | _ -> raise (RuntimeError "Invalid arguments to file_delete"))

   (* Command-line arguments *)
   | "argv" ->
       let args = Array.to_list Sys.argv in
       let script_args = match args with
         | _ :: _ :: rest -> rest  (* skip executable and filename *)
         | _ -> [] in
       (* Diagnostic: model frequently uses (argv) when input is in $0 as a
          single multi-line string. Detectable: length=1 AND that element
          contains a newline. ON by default; silence with SIGIL_DIAGNOSE=0. *)
       (if diagnose_enabled () then
         match script_args with
         | [single] when String.contains single '\n' ->
             Printf.eprintf
               "Warning: (argv) returned a 1-element list whose element contains \
                newlines. If you wanted to iterate input lines, use \
                (split $0 \"\\n\") instead — $0 is the first CLI argument as a \
                string; (argv) is the list of separate CLI arguments.\n"
         | _ -> ());
       VArray (ref (Array.of_list (List.map (fun s -> VString s) script_args)))

   | "argv_count" ->
       let count = max 0 (Array.length Sys.argv - 2) in
       VInt (Int64.of_int count)

   | "arg_int" | "argv_int" ->
       (* argv_int is the canonical name (matches argv/argv_count/arg_str family).
          arg_int is kept as legacy alias because the model frequently reaches for
          it. NOTE: this fetches CLI argv[i] parsed as int. To parse a STRING into
          int, use parse_int — they're different operations. The model has
          historically confused them on tasks like find_max_in_log. *)
       (match arg_vals with
        | [VInt n] ->
            let i = Int64.to_int n in
            let args = Array.to_list Sys.argv in
            let script_args = (match args with _ :: _ :: rest -> rest | _ -> []) in
            let arr = Array.of_list script_args in
            if i < 0 || i >= Array.length arr then
              raise (RuntimeError (func_name ^ ": index " ^ string_of_int i ^ " out of bounds"))
            else VInt (Int64.of_string arr.(i))
        | [VString _] ->
            raise (RuntimeError
              (func_name ^ ": takes an int CLI-arg index, not a string. " ^
               "To parse a string into int, use parse_int instead."))
        | _ -> raise (RuntimeError (func_name ^ " takes 1 int argument (CLI arg index)")))

   | "arg_str" ->
       (match arg_vals with
        | [VInt n] ->
            let i = Int64.to_int n in
            let args = Array.to_list Sys.argv in
            let script_args = (match args with _ :: _ :: rest -> rest | _ -> []) in
            let arr = Array.of_list script_args in
            if i < 0 || i >= Array.length arr then
              raise (RuntimeError ("arg_str: index " ^ string_of_int i ^ " out of bounds"))
            else VString arr.(i)
        | _ -> raise (RuntimeError "arg_str takes 1 int argument"))

   | "arg_float" ->
       (match arg_vals with
        | [VInt n] ->
            let i = Int64.to_int n in
            let args = Array.to_list Sys.argv in
            let script_args = (match args with _ :: _ :: rest -> rest | _ -> []) in
            let arr = Array.of_list script_args in
            if i < 0 || i >= Array.length arr then
              raise (RuntimeError ("arg_float: index " ^ string_of_int i ^ " out of bounds"))
            else VFloat (float_of_string arr.(i))
        | _ -> raise (RuntimeError "arg_float takes 1 int argument"))

   | "str" ->
       (* 1-arg: coerce to string. 2+ args: coerce each and concatenate.
          Matches the Python str()/JS String() + concat muscle memory. *)
       let coerce v = match v with
         | VInt n -> Int64.to_string n
         | VFloat f -> format_float_string f
         | VBool b -> if b then "true" else "false"
         | VDecimal s -> s
         | VString s -> s
         | other -> string_of_value other
       in
       (match arg_vals with
        | [] -> raise (RuntimeError "str requires at least 1 argument")
        | _ -> VString (String.concat "" (List.map coerce arg_vals)))

   | "len" ->
       (match arg_vals with
        | [VString s] -> VInt (Int64.of_int (String.length s))
        | [VArray arr] -> VInt (Int64.of_int (Array.length !arr))
        | [VMap (m, _)] -> VInt (Int64.of_int (Hashtbl.length m))
        | _ -> raise (RuntimeError "len takes 1 argument (string, array, or map)"))

   | "string_chars" ->
       (match arg_vals with
        | [VString s] ->
            let n = String.length s in
            let chars = List.init n (fun i -> VString (String.make 1 s.[i])) in
            VArray (ref (Array.of_list chars))
        | _ -> raise (RuntimeError "string_chars takes 1 string argument"))

   | "is_digit" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            VBool (c >= 48 && c <= 57)
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            VBool (c >= 48 && c <= 57)
        | _ -> raise (RuntimeError "is_digit takes 1 argument (int char code or single-char string)"))

   | "is_alpha" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            VBool ((c >= 65 && c <= 90) || (c >= 97 && c <= 122))
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            VBool ((c >= 65 && c <= 90) || (c >= 97 && c <= 122))
        | _ -> raise (RuntimeError "is_alpha takes 1 argument (int char code or single-char string)"))

   | "is_upper" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            VBool (c >= 65 && c <= 90)
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            VBool (c >= 65 && c <= 90)
        | _ -> raise (RuntimeError "is_upper takes 1 argument (int char code or single-char string)"))

   | "is_lower" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            VBool (c >= 97 && c <= 122)
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            VBool (c >= 97 && c <= 122)
        | _ -> raise (RuntimeError "is_lower takes 1 argument (int char code or single-char string)"))

   | "is_whitespace" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            VBool (c = 9 || c = 10 || c = 13 || c = 32)
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            VBool (c = 9 || c = 10 || c = 13 || c = 32)
        | _ -> raise (RuntimeError "is_whitespace takes 1 argument (int char code or single-char string)"))

   | "to_upper_char" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            if c >= 97 && c <= 122 then VInt (Int64.of_int (c - 32))
            else VInt code
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            if c >= 97 && c <= 122 then VString (String.make 1 (Char.chr (c - 32)))
            else VString s
        | _ -> raise (RuntimeError "to_upper_char takes 1 argument (int char code or single-char string)"))

   | "to_lower_char" ->
       (match arg_vals with
        | [VInt code] ->
            let c = Int64.to_int code in
            if c >= 65 && c <= 90 then VInt (Int64.of_int (c + 32))
            else VInt code
        | [VString s] when String.length s = 1 ->
            let c = Char.code s.[0] in
            if c >= 65 && c <= 90 then VString (String.make 1 (Char.chr (c + 32)))
            else VString s
        | _ -> raise (RuntimeError "to_lower_char takes 1 argument (int char code or single-char string)"))

   (* I/O *)
   | "print" ->
       output_emitted := true;
       (* Variadic: multiple args joined with space *)
       (match arg_vals with
        | [] -> VUnit
        | [v] -> print_string (string_of_value v); VUnit
        | vs ->
            let strs = List.map string_of_value vs in
            print_string (String.concat " " strs);
            VUnit)

  | "println" ->
      output_emitted := true;
      (* Variadic: multiple args joined with space, trailing newline.
         Tolerant of a trailing \n in the string (common model habit):
         if the last arg already ends with \n, use print_string instead to
         avoid doubling. *)
      let print_tolerant s =
        let n = String.length s in
        if n > 0 && s.[n-1] = '\n' then print_string s
        else print_endline s
      in
      (match arg_vals with
       | [] -> print_newline (); VUnit
       | [v] -> print_tolerant (string_of_value v); VUnit
       | vs ->
           let strs = List.map string_of_value vs in
           print_tolerant (String.concat " " strs);
           VUnit)

  | "read_line" ->
      VString (read_line ())

   | "stdin_read_all" ->
       let buf = Buffer.create 4096 in
       (try
         while true do
           let line = Stdlib.input_line Stdlib.stdin in
           Buffer.add_string buf line;
           Buffer.add_char buf '\n'
         done;
         VString (Buffer.contents buf)
       with End_of_file ->
         VString (Buffer.contents buf))

  (* ===== Short aliases for verbose builtins ===== *)
  | "split" ->
      (* Multi-char separator split. Accepts either (str, sep) or (sep, str)
         since LLMs frequently swap the order. *)
      let do_split s sep =
        if sep = "" then VArray (ref [|VString s|])
        else begin
          let slen = String.length s in
          let seplen = String.length sep in
          let parts = ref [] in
          let start = ref 0 in
          let i = ref 0 in
          while !i <= slen - seplen do
            if String.sub s !i seplen = sep then begin
              parts := String.sub s !start (!i - !start) :: !parts;
              i := !i + seplen;
              start := !i
            end else
              i := !i + 1
          done;
          parts := String.sub s !start (slen - !start) :: !parts;
          VArray (ref (Array.of_list (List.rev_map (fun p -> VString p) !parts)))
        end
      in
      (match arg_vals with
       | [VString s; VString sep] -> do_split s sep
       | _ -> raise (RuntimeError "split takes (string, string)"))

  | "join" ->
      (* Accept (array, sep) or (sep, array) — LLMs often swap. *)
      let do_join arr sep =
        let strs = Array.to_list arr |> List.map (fun v ->
          match v with VString s -> s | _ -> string_of_value v) in
        VString (String.concat sep strs)
      in
      (match arg_vals with
       | [VArray arr; VString sep] -> do_join !arr sep
       | [VString sep; VArray arr] -> do_join !arr sep
       | _ -> raise (RuntimeError "join takes (array, string)"))

  | "push" ->
      (match arg_vals with
       | [VArray arr; v] ->
           arr := Array.append !arr [|v|];
           VArray arr
       | _ -> raise (RuntimeError "push takes (array, value)"))

  | "chars" ->
      (match arg_vals with
       | [VString s] ->
           let n = String.length s in
           let chars = List.init n (fun i -> VString (String.make 1 s.[i])) in
           VArray (ref (Array.of_list chars))
       | _ -> raise (RuntimeError "chars takes 1 string"))

  | "sort" ->
      (match arg_vals with
       | [VArray arr] ->
           let sorted = Array.copy !arr in
           Array.sort (fun a b ->
             match a, b with
             | VInt x, VInt y -> Int64.compare x y
             | VFloat x, VFloat y -> compare x y
             | VString x, VString y -> compare x y
             | _ -> compare a b
           ) sorted;
           arr := sorted;
           VArray arr
       | _ -> raise (RuntimeError "sort takes 1 array"))

  | "lower" ->
      (match arg_vals with
       | [VString s] -> VString (String.lowercase_ascii s)
       | _ -> raise (RuntimeError "lower takes 1 string"))

  | "upper" ->
      (match arg_vals with
       | [VString s] -> VString (String.uppercase_ascii s)
       | _ -> raise (RuntimeError "upper takes 1 string"))

  | "trim" ->
      (match arg_vals with
       | [VString s] -> VString (String.trim s)
       | _ -> raise (RuntimeError "trim takes 1 string"))

  | "string_repeat" | "repeat" ->
      (* (string_repeat s n) -> s concatenated n times. (repeat s n) is the
         short alias. n must be a non-negative int. *)
      (match arg_vals with
       | [VString s; VInt n] ->
           let n = Int64.to_int n in
           if n < 0 then raise (RuntimeError "string_repeat: count must be >= 0")
           else if n = 0 || s = "" then VString ""
           else
             let buf = Buffer.create (String.length s * n) in
             for _ = 1 to n do Buffer.add_string buf s done;
             VString (Buffer.contents buf)
       | _ -> raise (RuntimeError "string_repeat takes (string, int)"))

  | "string_at" | "char_at" ->
      (* (string_at s i) -> the 1-character string at index i. Distinct from
         string_get which returns the int char code. Models reach for "get me
         the i-th character as a string I can compare to other strings"; this
         is the meeting-halfway builtin for that intent. *)
      (match arg_vals with
       | [VString s; VInt i] ->
           let i = Int64.to_int i in
           let n = String.length s in
           if i < 0 || i >= n then
             raise (RuntimeError (Printf.sprintf
               "string_at: index %d out of bounds (length %d)" i n))
           else VString (String.make 1 s.[i])
       | _ -> raise (RuntimeError "string_at takes (string, int)"))

  | "repeat_each" ->
      (* (repeat_each coll n) -> each element of coll repeated n times in
         place. (repeat_each "abc" 3) -> "aaabbbccc".
         (repeat_each [1 2 3] 2) -> [1 1 2 2 3 3]. Saves the model from
         (join (map_arr coll (\x (repeat x n))) "") gymnastics. *)
      (match arg_vals with
       | [VString s; VInt n] ->
           let n = Int64.to_int n in
           if n <= 0 then VString ""
           else
             let buf = Buffer.create (String.length s * n) in
             String.iter (fun c ->
               for _ = 1 to n do Buffer.add_char buf c done) s;
             VString (Buffer.contents buf)
       | [VArray arr; VInt n] ->
           let n = Int64.to_int n in
           if n <= 0 then VArray (ref [||])
           else
             let src = !arr in
             let out = Array.make (Array.length src * n) VUnit in
             Array.iteri (fun i v ->
               for j = 0 to n - 1 do out.(i * n + j) <- v done) src;
             VArray (ref out)
       | _ -> raise (RuntimeError "repeat_each takes (string|array, int)"))

  | "zip" ->
      (* (zip a b) -> position-wise interleave of two collections. The
         tail of the longer one is appended after the interleaved prefix.
         Output is an array of strings (string args) or array of values
         (array args). Models reach for explicit index-walks and get
         off-by-one; this absorbs that. *)
      let interleave_strs sa sb =
        let na = String.length sa and nb = String.length sb in
        let buf = Buffer.create (na + nb) in
        let mn = min na nb in
        for i = 0 to mn - 1 do
          Buffer.add_char buf sa.[i];
          Buffer.add_char buf sb.[i]
        done;
        if na > nb then Buffer.add_substring buf sa mn (na - mn)
        else if nb > na then Buffer.add_substring buf sb mn (nb - mn);
        Buffer.contents buf
      in
      (match arg_vals with
       | [VString sa; VString sb] -> VString (interleave_strs sa sb)
       | [VArray a; VArray b] ->
           let la = Array.length !a and lb = Array.length !b in
           let mn = min la lb in
           let out = Array.make (la + lb) VUnit in
           let pos = ref 0 in
           for i = 0 to mn - 1 do
             out.(!pos) <- !a.(i); incr pos;
             out.(!pos) <- !b.(i); incr pos
           done;
           if la > lb then
             for i = mn to la - 1 do out.(!pos) <- !a.(i); incr pos done
           else
             for i = mn to lb - 1 do out.(!pos) <- !b.(i); incr pos done;
           VArray (ref out)
       | _ -> raise (RuntimeError "zip takes (string,string) or (array,array)"))

  | "common_prefix" ->
      (* Longest common prefix of two strings. Returns the prefix as a string.
         Saves the model from manual char-walk loops with off-by-one bugs. *)
      (match arg_vals with
       | [VString a; VString b] ->
           let n = min (String.length a) (String.length b) in
           let i = ref 0 in
           while !i < n && a.[!i] = b.[!i] do incr i done;
           VString (String.sub a 0 !i)
       | _ -> raise (RuntimeError
           ("common_prefix takes (string, string), got " ^ fmt_arg_types arg_vals)))

  | "common_suffix" ->
      (* Longest common suffix of two strings. Returns the suffix as a string.
         The reverse-index loop is exactly where the model trips on
         (sub len_a i 1) arity confusion — this absorbs the failure shape. *)
      (match arg_vals with
       | [VString a; VString b] ->
           let na = String.length a and nb = String.length b in
           let n = min na nb in
           let i = ref 0 in
           while !i < n && a.[na - 1 - !i] = b.[nb - 1 - !i] do incr i done;
           VString (String.sub a (na - !i) !i)
       | _ -> raise (RuntimeError
           ("common_suffix takes (string, string), got " ^ fmt_arg_types arg_vals)))

  | "is_subseq" ->
      (* (is_subseq haystack needle) -> bool. True if needle's characters
         appear in haystack in the same order (not necessarily contiguous).
         Two-pointer walk; the model kept failing this in synthesis because
         it lacks `break`. *)
      (match arg_vals with
       | [VString haystack; VString needle] ->
           let nh = String.length haystack and nn = String.length needle in
           if nn = 0 then VBool true
           else begin
             let i = ref 0 and j = ref 0 in
             while !i < nh && !j < nn do
               if haystack.[!i] = needle.[!j] then incr j;
               incr i
             done;
             VBool (!j = nn)
           end
       | [VArray haystack; VArray needle] ->
           let nh = Array.length !haystack and nn = Array.length !needle in
           if nn = 0 then VBool true
           else begin
             let i = ref 0 and j = ref 0 in
             let value_eq a b = match a, b with
               | VInt x, VInt y -> x = y
               | VFloat x, VFloat y -> x = y
               | VString x, VString y -> x = y
               | VBool x, VBool y -> x = y
               | _ -> a = b
             in
             while !i < nh && !j < nn do
               if value_eq (!haystack).(!i) (!needle).(!j) then incr j;
               incr i
             done;
             VBool (!j = nn)
           end
       | _ -> raise (RuntimeError
           ("is_subseq takes (string, string) or (array, array), got "
            ^ fmt_arg_types arg_vals)))

  | "is_rotation" ->
      (* (is_rotation a b) -> bool. True if b is a rotation of a (same
         length, b is a substring of a ++ a). Standard trick — the model
         knows it but reaches for it inconsistently. *)
      (match arg_vals with
       | [VString a; VString b] ->
           if String.length a <> String.length b then VBool false
           else if String.length a = 0 then VBool true
           else
             let doubled = a ^ a in
             let nb = String.length b in
             let nd = String.length doubled in
             let found = ref false in
             let i = ref 0 in
             while not !found && !i <= nd - nb do
               if String.sub doubled !i nb = b then found := true;
               incr i
             done;
             VBool !found
       | _ -> raise (RuntimeError
           ("is_rotation takes (string, string), got " ^ fmt_arg_types arg_vals)))

  | "edit_distance" | "levenshtein" ->
      (* (edit_distance a b) -> int Levenshtein distance. Insertions,
         deletions, substitutions all cost 1. Two-row DP, O(min(na,nb))
         memory. Frequently needed; manual synthesis is fragile. *)
      (match arg_vals with
       | [VString a; VString b] ->
           let na = String.length a and nb = String.length b in
           if na = 0 then VInt (Int64.of_int nb)
           else if nb = 0 then VInt (Int64.of_int na)
           else begin
             let prev = Array.make (nb + 1) 0 in
             let curr = Array.make (nb + 1) 0 in
             for j = 0 to nb do prev.(j) <- j done;
             for i = 1 to na do
               curr.(0) <- i;
               for j = 1 to nb do
                 let cost = if a.[i-1] = b.[j-1] then 0 else 1 in
                 let del = prev.(j) + 1 in
                 let ins = curr.(j-1) + 1 in
                 let sub = prev.(j-1) + cost in
                 curr.(j) <- min del (min ins sub)
               done;
               Array.blit curr 0 prev 0 (nb + 1)
             done;
             VInt (Int64.of_int prev.(nb))
           end
       | _ -> raise (RuntimeError
           ("edit_distance takes (string, string), got " ^ fmt_arg_types arg_vals)))

  | "common_chars" ->
      (* (common_chars a b) -> string containing the multiset intersection
         of characters from a and b, in the order they appear in a (each
         char emitted at most as many times as it occurs in b).
         (common_chars "abca" "ac") -> "ac".  (common_chars "hello" "world")
         -> "lo". Use (len (common_chars a b)) for the count form. *)
      (match arg_vals with
       | [VString a; VString b] ->
           (* Build a count-table of b's chars *)
           let counts = Array.make 256 0 in
           String.iter (fun c -> counts.(Char.code c) <- counts.(Char.code c) + 1) b;
           let buf = Buffer.create (String.length a) in
           String.iter (fun c ->
             let i = Char.code c in
             if counts.(i) > 0 then begin
               Buffer.add_char buf c;
               counts.(i) <- counts.(i) - 1
             end
           ) a;
           VString (Buffer.contents buf)
       | _ -> raise (RuntimeError
           ("common_chars takes (string, string), got " ^ fmt_arg_types arg_vals)))

  | "swapcase" ->
      (match arg_vals with
       | [VString s] ->
           let buf = Bytes.of_string s in
           for i = 0 to Bytes.length buf - 1 do
             let c = Bytes.get buf i in
             if c >= 'a' && c <= 'z' then
               Bytes.set buf i (Char.chr (Char.code c - 32))
             else if c >= 'A' && c <= 'Z' then
               Bytes.set buf i (Char.chr (Char.code c + 32))
           done;
           VString (Bytes.to_string buf)
       | _ -> raise (RuntimeError "swapcase takes 1 string"))

  | "title" ->
      (* Capitalize first letter of each whitespace-separated word. *)
      (match arg_vals with
       | [VString s] ->
           let buf = Bytes.of_string s in
           let n = Bytes.length buf in
           let at_start = ref true in
           for i = 0 to n - 1 do
             let c = Bytes.get buf i in
             if c = ' ' || c = '\t' || c = '\n' then at_start := true
             else begin
               if !at_start && c >= 'a' && c <= 'z' then
                 Bytes.set buf i (Char.chr (Char.code c - 32))
               else if (not !at_start) && c >= 'A' && c <= 'Z' then
                 Bytes.set buf i (Char.chr (Char.code c + 32));
               at_start := false
             end
           done;
           VString (Bytes.to_string buf)
       | _ -> raise (RuntimeError "title takes 1 string"))

  | "uniq" ->
      (* Dedupe array preserving order of first occurrence. *)
      (match arg_vals with
       | [VArray arr] ->
           let seen = ref [] in
           let keep = ref [] in
           Array.iter (fun v ->
             if not (List.exists (fun x -> values_equal x v) !seen) then begin
               seen := v :: !seen;
               keep := v :: !keep
             end
           ) !arr;
           VArray (ref (Array.of_list (List.rev !keep)))
       | _ -> raise (RuntimeError "uniq takes 1 array"))

  | "parse_pairs" ->
      (* Parse "a=1,b=2" style into map. (parse_pairs str outer inner) *)
      (match arg_vals with
       | [VString s; VString outer; VString inner] when outer <> "" && inner <> "" ->
           let pairs = String.split_on_char outer.[0] s in
           let tbl = Hashtbl.create (List.length pairs) in
           let keys = ref [] in
           List.iter (fun p ->
             match String.split_on_char inner.[0] p with
             | k :: rest when rest <> [] ->
                 let v = String.concat (String.make 1 inner.[0]) rest in
                 if not (Hashtbl.mem tbl k) then keys := k :: !keys;
                 Hashtbl.replace tbl k (VString v)
             | _ -> ()
           ) pairs;
           VMap (tbl, ref (List.rev !keys))
       | _ -> raise (RuntimeError "parse_pairs takes (string, outer:string, inner:string)"))

  | "int" ->
      (match arg_vals with
       | [VString s] ->
           (try VInt (Int64.of_string (String.trim s))
            with Failure _ -> raise (RuntimeError ("int: cannot parse: " ^ s)))
       | [VFloat f] -> VInt (Int64.of_float f)
       | [VInt n] -> VInt n
       | _ -> raise (RuntimeError "int takes 1 string/float/int"))

  | "float" ->
      (match arg_vals with
       | [VString s] ->
           (try VFloat (float_of_string (String.trim s))
            with Failure _ -> raise (RuntimeError ("float: cannot parse: " ^ s)))
       | [VInt n] -> VFloat (Int64.to_float n)
       | [VFloat f] -> VFloat f
       | _ -> raise (RuntimeError "float takes 1 string/int/float"))

  | "parse_ints" ->
      (* Split string by separator and parse each piece as int, in one step.
         Common pattern: "1 2 3 4 5" -> [1 2 3 4 5]. *)
      (match arg_vals with
       | [VString s; VString sep] ->
           let parts = if sep = "" then [s]
                       else String.split_on_char sep.[0] s in
           let ints = List.filter_map (fun p ->
             let p = String.trim p in
             if p = "" then None
             else try Some (VInt (Int64.of_string p))
                  with Failure _ -> raise (RuntimeError ("parse_ints: cannot parse: " ^ p))
           ) parts in
           VArray (ref (Array.of_list ints))
       | [VString s] ->
           (* Default separator: any whitespace *)
           let parts = String.split_on_char ' ' s in
           let ints = List.filter_map (fun p ->
             let p = String.trim p in
             if p = "" then None
             else try Some (VInt (Int64.of_string p))
                  with Failure _ -> raise (RuntimeError ("parse_ints: cannot parse: " ^ p))
           ) parts in
           VArray (ref (Array.of_list ints))
       | _ -> raise (RuntimeError "parse_ints takes (string) or (string, separator)"))

  | "parse_int" | "str->int" ->
      (* Singular form. Accepts string or numeric value. Trims whitespace. *)
      (match arg_vals with
       | [VString s] ->
           (try VInt (Int64.of_string (String.trim s))
            with Failure _ -> raise (RuntimeError ("parse_int: cannot parse: " ^ s)))
       | [VInt n] -> VInt n
       | [VFloat f] -> VInt (Int64.of_float f)
       | _ -> raise (RuntimeError "parse_int takes (string) or numeric value"))

  | "count" ->
      (* (count haystack needle) — Python str.count / list.count semantics. *)
      (match arg_vals with
       | [VString s; VString sub] ->
           if sub = "" then VInt 0L
           else begin
             let n = String.length s and m = String.length sub in
             let c = ref 0 and i = ref 0 in
             while !i <= n - m do
               if String.sub s !i m = sub then begin
                 incr c; i := !i + m
               end else incr i
             done;
             VInt (Int64.of_int !c)
           end
       | [VArray arr; v] ->
           let c = Array.fold_left (fun acc e ->
             if values_equal e v then acc + 1 else acc) 0 !arr in
           VInt (Int64.of_int c)
       | _ -> raise (RuntimeError "count takes (string, string) or (array, value)"))

  | "enumerate" ->
      (* (enumerate arr) — Python enumerate(): array of [index, value] pairs. *)
      (match arg_vals with
       | [VArray arr] ->
           let pairs = Array.mapi (fun i v ->
             VArray (ref [| VInt (Int64.of_int i); v |])
           ) !arr in
           VArray (ref pairs)
       | _ -> raise (RuntimeError "enumerate takes 1 array"))

  | "scan" ->
      (* (scan arr fn init) — Haskell scanl / Python itertools.accumulate.
         Returns an array of accumulator states AFTER each step.
         Output length = input length. Init is the seed (not prepended). *)
      (match arg_vals with
       | [VArray arr; fn; init] ->
           let acc = ref init in
           let out = Array.map (fun elem ->
             acc := invoke_callable env fn [!acc; elem] "scan";
             !acc
           ) !arr in
           VArray (ref out)
       | _ -> raise (RuntimeError "scan takes (array, function, init)"))

  | "map_kv" ->
      (* (map_kv m fn) — Python [fn(k, v) for k, v in m.items()].
         fn is called with (key, value) as two positional args, so a
         2-arg closure (\\(k v) body) destructures naturally without array_get.
         Accepts (fn, m) order too — the model often writes that shape. *)
      let do_map_kv m keys fn =
        let out = List.map (fun k ->
          invoke_callable env fn [VString k; Hashtbl.find m k] "map_kv"
        ) !keys in
        VArray (ref (Array.of_list out))
      in
      (match arg_vals with
       | [VMap (m, keys); fn] -> do_map_kv m keys fn
       | [fn; VMap (m, keys)] -> do_map_kv m keys fn
       | _ -> raise (RuntimeError ("map_kv takes (map, function) or (function, map), got " ^ fmt_arg_types arg_vals)))

  | "map_pairs" ->
      (* (map_pairs arr fn) — map over array of 2-element pair arrays,
         calling fn with the two elements as positional args. Natural fit
         for the output of enumerate / entries / zip. A 2-arg closure
         (\\(a b) body) destructures without array_get. *)
      (match arg_vals with
       | [VArray arr; fn] ->
           let out = Array.map (fun v ->
             match v with
             | VArray p when Array.length !p = 2 ->
                 invoke_callable env fn [!p.(0); !p.(1)] "map_pairs"
             | _ -> raise (RuntimeError
                 "map_pairs: every element must be a 2-element array")
           ) !arr in
           VArray (ref out)
       | _ -> raise (RuntimeError "map_pairs takes (array-of-pairs, function)"))

  | "diff" ->
      (* (diff a b) — elements in a not in b, preserving order of a. *)
      (match arg_vals with
       | [VArray a; VArray b] ->
           let kept = ref [] in
           Array.iter (fun v ->
             if not (Array.exists (fun x -> values_equal x v) !b) then
               kept := v :: !kept) !a;
           VArray (ref (Array.of_list (List.rev !kept)))
       | _ -> raise (RuntimeError "diff takes (array, array)"))

  | "inter" ->
      (* (inter a b) — elements in both a and b, preserving order of a, deduped. *)
      (match arg_vals with
       | [VArray a; VArray b] ->
           let kept = ref [] in
           Array.iter (fun v ->
             if Array.exists (fun x -> values_equal x v) !b &&
                not (List.exists (fun x -> values_equal x v) !kept) then
               kept := v :: !kept) !a;
           VArray (ref (Array.of_list (List.rev !kept)))
       | _ -> raise (RuntimeError "inter takes (array, array)"))

  | "union" ->
      (* (union a b) — elements from a then b, deduped, order preserved. *)
      (match arg_vals with
       | [VArray a; VArray b] ->
           let kept = ref [] in
           let add v = if not (List.exists (fun x -> values_equal x v) !kept) then
             kept := v :: !kept in
           Array.iter add !a;
           Array.iter add !b;
           VArray (ref (Array.of_list (List.rev !kept)))
       | _ -> raise (RuntimeError "union takes (array, array)"))

  | "fmt_float" ->
      (* (fmt_float x prec) — format number with `prec` decimal places.
         Accepts int, float, or decimal input. *)
      (match arg_vals with
       | [VFloat x; VInt p] ->
           VString (Printf.sprintf "%.*f" (Int64.to_int p) x)
       | [VInt x; VInt p] ->
           VString (Printf.sprintf "%.*f" (Int64.to_int p) (Int64.to_float x))
       | [VDecimal d; VInt p] ->
           let f = float_of_string d in
           VString (Printf.sprintf "%.*f" (Int64.to_int p) f)
       | _ -> raise (RuntimeError "fmt_float takes (number, int-precision)"))

  | "slice" ->
      (* (slice coll start end) — Python-style half-open slice on string or
         array. Negative start/end count from the right. If end is omitted
         (only 2 args), slice to the end. *)
      let resolve_bounds len s e =
        let norm i = if i < 0 then max 0 (len + i) else min len i in
        (norm s, norm e) in
      (match arg_vals with
       | [VArray arr; VInt s; VInt e] ->
           let len = Array.length !arr in
           let (s, e) = resolve_bounds len (Int64.to_int s) (Int64.to_int e) in
           if e <= s then VArray (ref [||])
           else VArray (ref (Array.sub !arr s (e - s)))
       | [VArray arr; VInt s] ->
           let len = Array.length !arr in
           let (s, _) = resolve_bounds len (Int64.to_int s) len in
           if len <= s then VArray (ref [||])
           else VArray (ref (Array.sub !arr s (len - s)))
       | [VString str; VInt s; VInt e] ->
           let len = String.length str in
           let (s, e) = resolve_bounds len (Int64.to_int s) (Int64.to_int e) in
           if e <= s then VString "" else VString (String.sub str s (e - s))
       | [VString str; VInt s] ->
           let len = String.length str in
           let (s, _) = resolve_bounds len (Int64.to_int s) len in
           if len <= s then VString "" else VString (String.sub str s (len - s))
       | _ -> raise (RuntimeError
           ("slice takes (string|array, int-start) or (string|array, int-start, int-end), got "
            ^ fmt_arg_types arg_vals)))

  | "merge" ->
      (* (merge m1 m2 ...) — rightmost key wins; order = keys of m1 then new
         keys from later maps. *)
      (match arg_vals with
       | [] -> raise (RuntimeError "merge takes at least 1 map")
       | maps ->
           let tbl = Hashtbl.create 16 in
           let keys = ref [] in
           List.iter (fun v ->
             match v with
             | VMap (src, src_keys) ->
                 List.iter (fun k ->
                   if not (Hashtbl.mem tbl k) then keys := k :: !keys;
                   Hashtbl.replace tbl k (Hashtbl.find src k)) !src_keys
             | _ -> raise (RuntimeError "merge takes maps")) maps;
           VMap (tbl, ref (List.rev !keys)))

  | "range" ->
      (* (range end) or (range start end) — int array [start, end). *)
      (match arg_vals with
       | [VInt e] ->
           let e = Int64.to_int e in
           VArray (ref (Array.init (max 0 e) (fun i -> VInt (Int64.of_int i))))
       | [VInt s; VInt e] ->
           let s = Int64.to_int s and e = Int64.to_int e in
           let n = max 0 (e - s) in
           VArray (ref (Array.init n (fun i -> VInt (Int64.of_int (s + i)))))
       | _ -> raise (RuntimeError "range takes (end) or (start, end)"))

  | "counter" ->
      (* (counter arr) — Python Counter. Returns map of string→int count.
         Keys are stringified via str conversion. *)
      (match arg_vals with
       | [VArray arr] ->
           let tbl = Hashtbl.create (Array.length !arr) in
           let keys = ref [] in
           Array.iter (fun v ->
             let k = match v with
               | VString s -> s
               | VInt n -> Int64.to_string n
               | _ -> string_of_value v in
             let cur = try (match Hashtbl.find tbl k with VInt n -> n | _ -> 0L) with Not_found -> 0L in
             if not (Hashtbl.mem tbl k) then keys := k :: !keys;
             Hashtbl.replace tbl k (VInt (Int64.add cur 1L))
           ) !arr;
           VMap (tbl, ref (List.rev !keys))
       | _ -> raise (RuntimeError "counter takes 1 array"))

  | "sort_by" ->
      (* (sort_by arr fn) — stable sort of arr.
         If fn takes 1 arg: it's a key function; sort ascending by key.
           For descending, negate the key: (sort_by arr (\x (neg (fn x)))).
         If fn takes 2 args: it's a comparator returning bool (true = a<b)
           or int (<0 = a<b). Matches the most common LLM expectation.
         Mutates the input ref AND returns it (same shape as `sort`), so
         both `(sort_by arr fn)` and `(set sorted (sort_by arr fn))` work. *)
      let arity_of v = match v with
        | VFunction (_, params, _, _) -> Some (List.length params)
        | VClosure (params, _, _) -> Some (List.length params)
        | _ -> None
      in
      (match arg_vals with
       | [VArray arr; fn] ->
           let n = Array.length !arr in
           (* Pair detection: if every array element is itself a 2-array
              and the lambda has 2 params, treat as a key function over
              pairs (auto-destructured) rather than a comparator. This is
              the dominant `(\(k v) ...)` intent over `(entries m)`. *)
           let all_pairs () =
             n > 0 &&
             Array.for_all (function VArray a -> Array.length !a = 2 | _ -> false) !arr
           in
           let effective_arity = match arity_of fn with
             | Some 2 when all_pairs () -> Some 1  (* treat as key fn over pairs *)
             | a -> a
           in
           let sorted = match effective_arity with
            | Some 2 ->
                let indexed = Array.init n (fun i -> (i, !arr.(i))) in
                Array.sort (fun (ia, va) (ib, vb) ->
                  let r = invoke_callable env fn [va; vb] "sort_by" in
                  let c = match r with
                    | VBool true -> -1
                    | VBool false ->
                        (match invoke_callable env fn [vb; va] "sort_by" with
                         | VBool true -> 1
                         | _ -> 0)
                    | VInt n -> Int64.compare n 0L
                    | VFloat f -> compare f 0.0
                    | _ -> raise (RuntimeError "sort_by comparator must return bool or int")
                  in
                  if c <> 0 then c else compare ia ib
                ) indexed;
                Array.map snd indexed
            | _ ->
                let keyed = Array.init n (fun i ->
                  (i, !arr.(i), invoke_callable env fn [!arr.(i)] "sort_by")
                ) in
                let cmp a b = match a, b with
                  | VInt x, VInt y -> Int64.compare x y
                  | VFloat x, VFloat y -> compare x y
                  | VString x, VString y -> compare x y
                  | VArray ax, VArray ay ->
                      let la = Array.to_list !ax and lb = Array.to_list !ay in
                      compare la lb
                  | _ -> compare a b in
                Array.sort (fun (ia, _, ka) (ib, _, kb) ->
                  let c = cmp ka kb in if c <> 0 then c else compare ia ib) keyed;
                Array.map (fun (_, v, _) -> v) keyed
           in
           arr := sorted;
           VArray arr
       | _ -> raise (RuntimeError "sort_by takes (array, function)"))

  | "group_by" ->
      (* (group_by arr fn) — returns map from key (stringified) to array of
         elements that fn mapped there. *)
      (match arg_vals with
       | [VArray arr; fn] ->
           let tbl = Hashtbl.create 16 in
           let keys = ref [] in
           Array.iter (fun v ->
             let k_val = invoke_callable env fn [v] "group_by" in
             let k = match k_val with
               | VString s -> s
               | VInt n -> Int64.to_string n
               | _ -> string_of_value k_val in
             let cur = match Hashtbl.find_opt tbl k with
               | Some (VArray r) -> r
               | _ -> let r = ref [||] in
                      keys := k :: !keys;
                      Hashtbl.add tbl k (VArray r); r in
             cur := Array.append !cur [|v|]
           ) !arr;
           VMap (tbl, ref (List.rev !keys))
       | _ -> raise (RuntimeError "group_by takes (array, function)"))

  | "transpose" ->
      (* (transpose rows) — matrix transpose. rows is an array of arrays.
         Shorter rows produce a rectangular transpose up to min length. *)
      (match arg_vals with
       | [VArray rows] ->
           let row_arrs = Array.map (fun v ->
             match v with VArray r -> r
                       | _ -> raise (RuntimeError "transpose: not a matrix")) !rows in
           let n_rows = Array.length row_arrs in
           if n_rows = 0 then VArray (ref [||])
           else begin
             let n_cols = Array.fold_left (fun acc r -> min acc (Array.length !r))
                            (Array.length !(row_arrs.(0))) row_arrs in
             let cols = Array.init n_cols (fun c ->
               VArray (ref (Array.init n_rows (fun r -> !(row_arrs.(r)).(c))))
             ) in
             VArray (ref cols)
           end
       | _ -> raise (RuntimeError "transpose takes (array of arrays)"))

  | "max_by" | "min_by" ->
      (* (max_by arr fn) — element of arr maximising fn; ties keep first.
         (min_by arr fn) — same but minimising. *)
      (match arg_vals with
       | [VArray arr; fn] ->
           let n = Array.length !arr in
           if n = 0 then raise (RuntimeError (func_name ^ ": empty array"))
           else begin
             let cmp a b = match a, b with
               | VInt x, VInt y -> Int64.compare x y
               | VFloat x, VFloat y -> compare x y
               | VString x, VString y -> compare x y
               | _ -> compare a b in
             let pick = if func_name = "max_by" then (>) else (<) in
             let best_idx = ref 0 in
             let best_key = ref (invoke_callable env fn [!arr.(0)] func_name) in
             for i = 1 to n - 1 do
               let k = invoke_callable env fn [!arr.(i)] func_name in
               if pick (cmp k !best_key) 0 then begin
                 best_idx := i; best_key := k
               end
             done;
             !arr.(!best_idx)
           end
       | _ -> raise (RuntimeError (func_name ^ " takes (array, function)")))

  | "digits" ->
      (* Digit array of a non-negative int, or of the digit chars of a string. *)
      (match arg_vals with
       | [VInt n] ->
           let n = Int64.to_int n in
           if n < 0 then raise (RuntimeError "digits: negative int")
           else if n = 0 then VArray (ref [| VInt 0L |])
           else begin
             let rec loop m acc = if m = 0 then acc else loop (m / 10) (VInt (Int64.of_int (m mod 10)) :: acc) in
             VArray (ref (Array.of_list (loop n [])))
           end
       | [VString s] ->
           let arr = ref [] in
           String.iter (fun c ->
             if c >= '0' && c <= '9' then
               arr := VInt (Int64.of_int (Char.code c - Char.code '0')) :: !arr
           ) s;
           VArray (ref (Array.of_list (List.rev !arr)))
       | _ -> raise (RuntimeError "digits takes 1 int or string"))

  | "sum" ->
      (* Sum an array of ints or floats *)
      (match arg_vals with
       | [VArray arr] ->
           if Array.length !arr = 0 then VInt 0L
           else begin
             let all_int = Array.for_all (fun v -> match v with VInt _ -> true | _ -> false) !arr in
             let all_float = Array.for_all (fun v -> match v with VFloat _ -> true | _ -> false) !arr in
             if all_int then
               VInt (Array.fold_left (fun acc v -> match v with VInt n -> Int64.add acc n | _ -> acc) 0L !arr)
             else if all_float then
               VFloat (Array.fold_left (fun acc v -> match v with VFloat f -> acc +. f | _ -> acc) 0.0 !arr)
             else raise (RuntimeError "sum: array must be homogeneous int or float")
           end
       | _ -> raise (RuntimeError "sum takes 1 array"))

  | "filter" ->
      (* (filter arr fn-or-closure) OR (filter fn-or-closure arr). Array-first
         is canonical Sigil; function-first is what Clojure/Python models reach
         for. Accept both. *)
      (match arg_vals with
       | [VArray arr; pred] | [pred; VArray arr] ->
           let kept = ref [] in
           Array.iter (fun elem ->
             let result = invoke_callable env pred [elem] "filter" in
             match result with
             | VBool true -> kept := elem :: !kept
             | _ -> ()
           ) !arr;
           VArray (ref (Array.of_list (List.rev !kept)))
       | _ -> raise (RuntimeError "filter takes (array, function) or (function, array)"))

  | "map_arr" ->
      (* (map_arr arr fn) OR (map_arr fn arr) — array-first canonical,
         function-first accepted for model ergonomics. *)
      (match arg_vals with
       | [VArray arr; fn] | [fn; VArray arr] ->
           let mapped = Array.map (fun elem ->
             invoke_callable env fn [elem] "map_arr"
           ) !arr in
           VArray (ref mapped)
       | _ -> raise (RuntimeError "map_arr takes (array, function) or (function, array)"))

  | "reduce" ->
      (* (reduce arr fn init) OR (reduce fn init arr) — both orders accepted.
         The latter is Clojure/Haskell style. *)
      (match arg_vals with
       | [VArray arr; fn; init] ->
           Array.fold_left (fun acc elem ->
             invoke_callable env fn [acc; elem] "reduce"
           ) init !arr
       | [fn; init; VArray arr] ->
           Array.fold_left (fun acc elem ->
             invoke_callable env fn [acc; elem] "reduce"
           ) init !arr
       | _ -> raise (RuntimeError "reduce takes (array, function, init) or (function, init, array)"))

  | "count_in" ->
      (* Count chars in string s that appear in string charset, or elements of array1 in array2 *)
      (match arg_vals with
       | [VString s; VString charset] ->
           let count = ref 0 in
           String.iter (fun c ->
             if String.contains charset c then incr count
           ) s;
           VInt (Int64.of_int !count)
       | [VArray needles; VArray haystack] ->
           let hs = !haystack in
           let count = ref 0 in
           Array.iter (fun n ->
             if Array.exists (fun h -> values_equal n h) hs then incr count
           ) !needles;
           VInt (Int64.of_int !count)
       | _ -> raise (RuntimeError "count_in takes (string, charset) or (array, array)"))

  | "map_inc" ->
      (* (map_inc m k) increments the int at key k, setting to 1 if missing *)
      (match arg_vals with
       | [VMap (m, keys); VString k] ->
           let cur = try Hashtbl.find m k with Not_found -> VInt 0L in
           (match cur with
            | VInt n ->
                let next = VInt (Int64.add n 1L) in
                if not (Hashtbl.mem m k) then keys := !keys @ [k];
                Hashtbl.replace m k next;
                next
            | _ -> raise (RuntimeError "map_inc: existing value at key is not int"))
       | _ -> raise (RuntimeError "map_inc takes (map, string)"))

  | "get_or" ->
      (* (get_or coll key_or_idx default) — get with fallback *)
      (match arg_vals with
       | [VMap (m, _); VString k; default] ->
           (try Hashtbl.find m k with Not_found -> default)
       | [VArray arr; VInt i; default] ->
           let idx = Int64.to_int i in
           if idx < 0 || idx >= Array.length !arr then default
           else !arr.(idx)
       | _ -> raise (RuntimeError "get_or takes (map, string, default) or (array, int, default)"))

  (* Time operations *)
  | "time_now" ->
      VInt (Int64.of_float (Unix.time ()))

  | "sleep" ->
      (match arg_vals with
       | [VInt ms] -> Unix.sleepf (Int64.to_float ms /. 1000.0); VUnit
       | _ -> raise (RuntimeError "Invalid arguments to sleep"))

   (* Process operations - stores (pid, stdin_fd, stdout_fd) *)
   | "process_spawn" ->
       (match arg_vals with
        | [VString cmd; VArray args_ref] ->
            let args = Array.of_list (List.map string_of_value (Array.to_list !args_ref)) in
            let argv = Array.concat [[|cmd|]; args] in
            let stdin_read, stdin_write = Unix.pipe () in
            let stdout_read, stdout_write = Unix.pipe () in
            let _pid = Unix.create_process cmd argv stdin_read stdout_write Unix.stderr in
            Unix.close stdin_read;
            Unix.close stdout_write;
            VChannel (stdin_write, stdout_read, Some _pid)
        | [VString cmd] ->
            let pid = Unix.create_process cmd [|cmd|] Unix.stdin Unix.stdout Unix.stderr in
            VProcess pid
        | _ -> raise (RuntimeError "Invalid arguments to process_spawn"))

   | "process_wait" ->
       (match arg_vals with
        | [VProcess pid] ->
            let _, status = Unix.waitpid [] pid in
            (match status with
             | Unix.WEXITED code -> VInt (Int64.of_int code)
             | _ -> VInt 0L)
        | [VChannel (stdin_write, stdout_read, pid_opt)] ->
            (* Close stdin so child process knows input is done, then wait *)
            (try Unix.close stdin_write with Unix.Unix_error _ -> ());
            (try Unix.close stdout_read with Unix.Unix_error _ -> ());
            let wait_pid = match pid_opt with Some p -> p | None -> -1 in
            let _, status = Unix.waitpid [] wait_pid in
            (match status with
             | Unix.WEXITED code -> VInt (Int64.of_int code)
             | _ -> VInt 0L)
        | _ -> raise (RuntimeError "Invalid arguments to process_wait"))

   | "process_write" ->
       (match arg_vals with
         | [VChannel (stdin_write, _, _); VString data] ->
            let bytes = Bytes.of_string data in
            let written = Unix.write stdin_write bytes 0 (Bytes.length bytes) in
            VBool (written > 0)
        | _ -> raise (RuntimeError "Invalid arguments to process_write"))

   | "process_read" ->
       (match arg_vals with
        | [VChannel (_, stdout_read, _)] ->
            let ready, _, _ = Unix.select [stdout_read] [] [] 0.05 in
            if ready = [] then VString ""
            else begin
              Unix.set_nonblock stdout_read;
              let result = (try
                let buf = Bytes.create 4096 in
                let received = Unix.read stdout_read buf 0 4096 in
                if received > 0 then
                  Bytes.to_string (Bytes.sub buf 0 received)
                else ""
              with Unix.Unix_error ((Unix.EAGAIN | Unix.EWOULDBLOCK), _, _) -> "") in
              Unix.clear_nonblock stdout_read;
              VString result
            end
        | [VProcess _pid] ->
            raise (RuntimeError "process_read requires a VChannel from process_spawn with pipes, not a bare PID")
        | _ -> raise (RuntimeError "Invalid arguments to process_read"))

   | "process_kill" ->
       (match arg_vals with
        | [VProcess pid; VInt sig_num] ->
            Unix.kill pid (Int64.to_int sig_num);
            VBool true
        | _ -> raise (RuntimeError "Invalid arguments to process_kill"))

  | "process_exec" ->
      (match arg_vals with
       | [VString cmd] ->
           let _, status = Unix.waitpid [] (Unix.create_process cmd [|cmd|] Unix.stdin Unix.stdout Unix.stderr) in
           (match status with
            | Unix.WEXITED code -> VInt (Int64.of_int code)
            | Unix.WSIGNALED _ -> VInt (-1L)
            | Unix.WSTOPPED _ -> VInt (-1L))
       | _ -> raise (RuntimeError "Invalid arguments to process_exec"))

  (* TCP operations *)
   | "tcp_listen" ->
       (match arg_vals with
        | [VInt port] ->
            let sock = Unix.socket Unix.PF_INET Unix.SOCK_STREAM 0 in
            Unix.setsockopt sock Unix.SO_REUSEADDR true;
            Unix.bind sock (Unix.ADDR_INET (Unix.inet_addr_any, Int64.to_int port));
            Unix.listen sock 5;
            VSocket sock
        | _ -> raise (RuntimeError "Invalid arguments to tcp_listen"))

  | "tcp_accept" ->
      (match arg_vals with
       | [VSocket sock] ->
           let client_sock, _ = Unix.accept sock in
           VSocket client_sock
       | _ -> raise (RuntimeError "Invalid arguments to tcp_accept"))

   | "tcp_connect" ->
       (match arg_vals with
        | [VString host; VInt port] ->
            let sock = Unix.socket Unix.PF_INET Unix.SOCK_STREAM 0 in
            let host_addr = (Unix.gethostbyname host).Unix.h_addr_list.(0) in
            Unix.connect sock (Unix.ADDR_INET (host_addr, Int64.to_int port));
            VSocket sock
        | _ -> raise (RuntimeError "Invalid arguments to tcp_connect"))

  | "tcp_send" ->
      (match arg_vals with
       | [VSocket sock; VString data] ->
           let bytes = Bytes.of_string data in
           let sent = Unix.write sock bytes 0 (String.length data) in
           VInt (Int64.of_int sent)
       | [VTlsSocket ssl_sock; VString data] ->
           let sent = Ssl.write_substring ssl_sock data 0 (String.length data) in
           VInt (Int64.of_int sent)
       | _ -> raise (RuntimeError "Invalid arguments to tcp_send"))

   | "tcp_receive" ->
       (match arg_vals with
        | [VSocket sock; VInt max_bytes] ->
            let buf = Bytes.create (Int64.to_int max_bytes) in
            let received = Unix.read sock buf 0 (Int64.to_int max_bytes) in
            if received > 0 then
              VString (Bytes.sub_string buf 0 received)
            else
              VString ""
        | [VSocket sock] ->
            let buf = Bytes.create 4096 in
            let received = Unix.read sock buf 0 4096 in
            if received > 0 then
              VString (Bytes.sub_string buf 0 received)
            else
              VString ""
        | [VTlsSocket ssl_sock; VInt max_bytes] ->
            let buf = Bytes.create (Int64.to_int max_bytes) in
            let received = Ssl.read ssl_sock buf 0 (Int64.to_int max_bytes) in
            if received > 0 then
              VString (Bytes.sub_string buf 0 received)
            else
              VString ""
        | [VTlsSocket ssl_sock] ->
            let buf = Bytes.create 4096 in
            let received = Ssl.read ssl_sock buf 0 4096 in
            if received > 0 then
              VString (Bytes.sub_string buf 0 received)
            else
              VString ""
        | _ -> raise (RuntimeError "Invalid arguments to tcp_receive"))

  | "tcp_close" ->
      (match arg_vals with
       | [VSocket sock] -> Unix.close sock; VUnit
       | [VTlsSocket ssl_sock] ->
           (try Ssl.shutdown ssl_sock with _ -> ());
           VUnit
       | _ -> raise (RuntimeError "Invalid arguments to tcp_close"))

   | "socket_select" ->
       (match arg_vals with
        | [VArray inputs_ref] ->
            let inputs = Array.to_list !inputs_ref in
            let fds = List.mapi (fun i v ->
              match v with
              | VSocket fd -> Some (i, fd)
              | VWsSocket (WsPlain fd) -> Some (i, fd)
              | VWsSocket (WsTls ssl) -> Some (i, Ssl.file_descr_of_socket ssl)
              | _ -> None
            ) inputs in
            let valid_fds = List.filter_map (fun x -> x) fds in
            let fd_list = List.map snd valid_fds in
            let readable, _, _ = Unix.select fd_list [] [] 0.01 in
            let result = ref [||] in
            List.iter (fun (idx, fd) ->
              if List.mem fd readable then begin
                let new_result = Array.make (Array.length !result + 1) (VInt 0L) in
                Array.blit !result 0 new_result 0 (Array.length !result);
                new_result.(Array.length !result) <- VInt (Int64.of_int idx);
                result := new_result
              end
            ) valid_fds;
            VArray result
         | _ -> raise (RuntimeError "Invalid arguments to socket_select"))

  (* Channel operations *)
  | "channel_new" ->
      let read_fd, write_fd = Unix.pipe () in
      VChannel (read_fd, write_fd, None)

   | "channel_send" ->
       (match arg_vals with
        | [VChannel (_, write_fd, _); v] ->
            (* Tagged serialization: prepend type tag for channel_recv *)
            let tagged_data = match v with
              | VInt n -> "i" ^ Int64.to_string n
              | VFloat f -> "f" ^ string_of_float f
              | VBool b -> "b" ^ (if b then "true" else "false")
              | VString s -> "s" ^ s
              | _ -> "s" ^ string_of_value v
            in
            let len = String.length tagged_data in
            let len_bytes = Bytes.create 4 in
            Bytes.set_int32_le len_bytes 0 (Int32.of_int len);
            ignore (Unix.write write_fd len_bytes 0 4);
            let bytes = Bytes.of_string tagged_data in
            ignore (Unix.write write_fd bytes 0 len);
            VUnit
        | _ -> raise (RuntimeError "Invalid arguments to channel_send"))

  | "channel_recv" ->
      (match arg_vals with
       | [VChannel (read_fd, _, _)] ->
           let len_bytes = Bytes.create 4 in
           let _ = Unix.read read_fd len_bytes 0 4 in
           let len = Int32.to_int (Bytes.get_int32_le len_bytes 0) in
           let buf = Bytes.create len in
           let received = Unix.read read_fd buf 0 len in
           if received > 0 then
             let s = Bytes.sub_string buf 0 received in
             (* Tagged deserialization: first char is type tag *)
             if String.length s >= 2 then
               let tag = s.[0] in
               let payload = String.sub s 1 (String.length s - 1) in
               match tag with
               | 'i' -> (try VInt (Int64.of_string payload)
                         with _ -> VString s)
               | 'f' -> (try VFloat (float_of_string payload)
                         with _ -> VString s)
               | 'b' -> if payload = "true" then VBool true
                        else if payload = "false" then VBool false
                        else VString s
               | 's' -> VString payload
               | _ -> VString s  (* Unknown tag, return raw *)
             else
               VString s
           else
             VUnit
       | _ -> raise (RuntimeError "Invalid arguments to channel_recv"))

  (* Regex operations — backed by the Re library (Perl-compatible).
     Re.Perl.compile_pat handles \b, \d, \w, \s, non-greedy *? +?, named
     groups, anchors, character classes, alternation — i.e. the syntax
     models actually write. The earlier Str backend rejected most of these,
     causing a long tail of "regex matched nothing" failures. The
     regex_translate_braces helper above is no longer needed (Re supports
     {n,m} natively) but is kept for backward-compat callers if any. *)
  | "regex_compile" ->
      (match arg_vals with
       | [VString pattern] -> VString pattern  (* Store pattern as string; compiled at use site *)
       | _ -> raise (RuntimeError "Invalid arguments to regex_compile"))

  | "regex_match" ->
      (match arg_vals with
       | [VString pattern; VString text] ->
           (try
             let re = Re.Perl.compile_pat pattern in
             VBool (Re.execp re text)
           with Re.Perl.Parse_error -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern))
              | Re.Perl.Not_supported -> raise (RuntimeError ("Regex feature not supported: " ^ pattern)))
       | _ -> raise (RuntimeError "Invalid arguments to regex_match"))

  | "regex_find" ->
      (match arg_vals with
       | [VString pattern; VString text] ->
           (try
             let re = Re.Perl.compile_pat pattern in
             match Re.exec_opt re text with
             | Some g -> VString (Re.Group.get g 0)
             | None -> VString ""
           with Re.Perl.Parse_error -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern))
              | Re.Perl.Not_supported -> raise (RuntimeError ("Regex feature not supported: " ^ pattern)))
       | _ -> raise (RuntimeError "Invalid arguments to regex_find"))

  | "regex_find_all" ->
      (match arg_vals with
       | [VString pattern; VString text] ->
           (try
             let re = Re.Perl.compile_pat pattern in
             let matches = Re.all re text in
             let results = List.map (fun g -> VString (Re.Group.get g 0)) matches in
             VArray (ref (Array.of_list results))
           with Re.Perl.Parse_error -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern))
              | Re.Perl.Not_supported -> raise (RuntimeError ("Regex feature not supported: " ^ pattern)))
       | _ -> raise (RuntimeError "Invalid arguments to regex_find_all"))

   | "regex_replace" ->
       (match arg_vals with
        | [VString pattern; VString text; VString replacement] ->
            (try
              let re = Re.Perl.compile_pat pattern in
              VString (Re.replace re ~f:(fun _ -> replacement) text)
            with Re.Perl.Parse_error -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern))
               | Re.Perl.Not_supported -> raise (RuntimeError ("Regex feature not supported: " ^ pattern)))
        | _ -> raise (RuntimeError "Invalid arguments to regex_replace"))

  (* Directory operations *)
  | "dir_list" ->
      (match arg_vals with
       | [VString path] ->
           try
             let entries = Sys.readdir path in
             let arr = Array.map (fun f -> VString f) entries in
             VArray (ref arr)
           with Sys_error _ ->
             VArray (ref [||])
       | _ -> raise (RuntimeError "Invalid arguments to dir_list"))

  | "dir_create" ->
      (match arg_vals with
       | [VString path] ->
           (try
             Unix.mkdir path 0o755;
             VBool true
           with Unix.Unix_error (e, _, _) ->
             raise (RuntimeError ("dir_create failed: " ^ Unix.error_message e)))
       | _ -> raise (RuntimeError "Invalid arguments to dir_create"))

  | "dir_delete" ->
      (match arg_vals with
       | [VString path] ->
           (try
             Unix.rmdir path;
             VBool true
           with Unix.Unix_error (e, _, _) ->
             raise (RuntimeError ("dir_delete failed: " ^ Unix.error_message e)))
       | _ -> raise (RuntimeError "Invalid arguments to dir_delete"))

   (* JSON operations - implemented using maps and arrays *)
   | "json_new_object" ->
       make_vmap ()

   | "json_new_array" ->
       VArray (ref [||])

   | "json_parse" ->
       (match arg_vals with
        | [VString s] ->
            (* Simple JSON parser: handles objects, arrays, strings, numbers, booleans *)
            let s = String.trim s in
            let rec parse_json_value str pos =
              let pos = skip_whitespace str pos in
              if pos >= String.length str then raise (RuntimeError "Unexpected end of JSON input")
              else match str.[pos] with
              | '{' -> parse_json_object str (pos + 1)
              | '[' -> parse_json_array str (pos + 1)
              | '"' -> parse_json_string str (pos + 1)
              | 't' when pos + 3 < String.length str && String.sub str pos 4 = "true" ->
                  (VBool true, pos + 4)
              | 'f' when pos + 4 < String.length str && String.sub str pos 5 = "false" ->
                  (VBool false, pos + 5)
              | 'n' when pos + 3 < String.length str && String.sub str pos 4 = "null" ->
                  (VUnit, pos + 4)
              | c when c = '-' || (c >= '0' && c <= '9') -> parse_json_number str pos
              | _ -> raise (RuntimeError (Printf.sprintf "Unexpected character '%c' at position %d in JSON" str.[pos] pos))
            and skip_whitespace str pos =
              if pos >= String.length str then pos
              else match str.[pos] with
              | ' ' | '\t' | '\n' | '\r' -> skip_whitespace str (pos + 1)
              | _ -> pos
            and parse_json_string str pos =
              let buf = Buffer.create 64 in
              let rec loop i =
                if i >= String.length str then (VString (Buffer.contents buf), i)
                else match str.[i] with
                | '"' -> (VString (Buffer.contents buf), i + 1)
                | '\\' when i + 1 < String.length str ->
                    (match str.[i+1] with
                     | '"' -> Buffer.add_char buf '"'; loop (i + 2)
                     | '\\' -> Buffer.add_char buf '\\'; loop (i + 2)
                     | 'n' -> Buffer.add_char buf '\n'; loop (i + 2)
                     | 't' -> Buffer.add_char buf '\t'; loop (i + 2)
                     | '/' -> Buffer.add_char buf '/'; loop (i + 2)
                     | _ -> Buffer.add_char buf str.[i+1]; loop (i + 2))
                | c -> Buffer.add_char buf c; loop (i + 1)
              in
              loop pos
            and parse_json_number str pos =
              let start = pos in
              let is_float = ref false in
              let rec loop i =
                if i >= String.length str then i
                else match str.[i] with
                | '0'..'9' | '-' -> loop (i + 1)
                | '.' | 'e' | 'E' | '+' -> is_float := true; loop (i + 1)
                | _ -> i
              in
              let end_pos = loop pos in
              let num_str = String.sub str start (end_pos - start) in
              if !is_float then
                (try (VFloat (float_of_string num_str), end_pos)
                 with _ -> raise (RuntimeError ("Invalid JSON number: " ^ num_str)))
              else
                (try (VInt (Int64.of_string num_str), end_pos)
                 with _ -> raise (RuntimeError ("Invalid JSON number: " ^ num_str)))
            and parse_json_object str pos =
              let m = Hashtbl.create 16 in
              let keys = ref [] in
              let rec loop pos =
                let pos = skip_whitespace str pos in
                if pos >= String.length str then (VMap (m, keys), pos)
                else match str.[pos] with
                | '}' -> (VMap (m, keys), pos + 1)
                | ',' -> loop (pos + 1)
                | '"' ->
                    let (key, pos) = parse_json_string str (pos + 1) in
                    let key_str = match key with VString s -> s | _ -> "" in
                    let pos = skip_whitespace str pos in
                    let pos = if pos < String.length str && str.[pos] = ':' then pos + 1 else pos in
                    let (value, pos) = parse_json_value str pos in
                    vmap_set m keys key_str value;
                    loop pos
                | _ -> (VMap (m, keys), pos)
              in
              loop pos
            and parse_json_array str pos =
              let items = ref [||] in
              let rec loop pos =
                let pos = skip_whitespace str pos in
                if pos >= String.length str then (VArray (ref !items), pos)
                else match str.[pos] with
                | ']' -> (VArray (ref !items), pos + 1)
                | ',' -> loop (pos + 1)
                | _ ->
                    let (value, pos) = parse_json_value str pos in
                    items := Array.append !items [|value|];
                    loop pos
              in
              loop pos
            in
            let (result, _) = parse_json_value s 0 in
            result
        | _ -> raise (RuntimeError "Invalid arguments to json_parse"))

   | "json_stringify" ->
       (match arg_vals with
        | [v] ->
            let rec stringify = function
              | VMap (m, keys) ->
                  let pairs = List.filter_map (fun k ->
                    match Hashtbl.find_opt m k with
                    | Some v -> Some (Printf.sprintf "\"%s\":%s" (String.escaped k) (stringify v))
                    | None -> None
                  ) !keys in
                  "{" ^ String.concat "," pairs ^ "}"
              | VArray arr ->
                  let items = Array.to_list !arr in
                  "[" ^ String.concat "," (List.map stringify items) ^ "]"
              | VString s -> Printf.sprintf "\"%s\"" (String.escaped s)
              | VInt n -> Int64.to_string n
              | VFloat f -> string_of_float f
              | VBool b -> string_of_bool b
              | VUnit -> "null"
              | v -> string_of_value v
            in
            VString (stringify v)
        | _ -> raise (RuntimeError "Invalid arguments to json_stringify"))

    | "json_get" ->
        (* Array-of-keys (Clojure get-in style): (json_get j ["users" 0 "name"]).
           Each key is a string (map lookup) or int (array index). String keys
           that parse as int also work for arrays so `(json_get j (split p "."))`
           on a path-from-string works without manual int conversion.
           Empty array returns the node unchanged. *)
        (match arg_vals with
         | [node; VArray keys] -> json_walk_keys node !keys
         | [VMap (m, _); VString k] ->
             (try Hashtbl.find m k
              with Not_found -> raise (RuntimeError ("Key not found in JSON object: " ^ k)))
         | [VArray arr; VInt idx] ->
             let i = Int64.to_int idx in
             if i >= 0 && i < Array.length !arr then !arr.(i)
             else raise (RuntimeError ("JSON array index out of bounds: " ^ Int64.to_string idx))
         | _ -> raise (RuntimeError "Invalid arguments to json_get"))

    | "json_set" ->
        (* Array-of-keys: (json_set j ["users" 0 "name"] v) walks to parent then
           sets the final segment. Mutates in place; returns the root node. *)
        (match arg_vals with
         | [root; VArray keys; v] ->
             let ks = !keys in
             if Array.length ks = 0 then
               raise (RuntimeError "json_set: empty key array")
             else begin
               let (parent, last) = json_walk_parent root ks in
               (match parent, last with
                | VMap (m, ks_ref), VString k -> vmap_set m ks_ref k v
                | VArray arr, VInt idx ->
                    let i = Int64.to_int idx in
                    if i >= 0 && i < Array.length !arr then (!arr).(i) <- v
                    else raise (RuntimeError ("JSON array index out of bounds: " ^ Int64.to_string idx))
                | VArray arr, VString s ->
                    (try
                      let i = int_of_string s in
                      if i >= 0 && i < Array.length !arr then (!arr).(i) <- v
                      else raise (RuntimeError ("JSON array index out of bounds: " ^ s))
                    with Failure _ ->
                      raise (RuntimeError ("Cannot set array with non-integer segment: " ^ s)))
                | _ -> raise (RuntimeError "json_set: invalid parent / segment combination"));
               root
             end
         | [VMap (m, keys); VString k; v] ->
             vmap_set m keys k v;
             VMap (m, keys)
         | [VArray arr; VInt idx; v] ->
             let i = Int64.to_int idx in
             if i >= 0 && i < Array.length !arr then begin
               (!arr).(i) <- v;
               VArray arr
             end else
               raise (RuntimeError ("JSON array index out of bounds: " ^ Int64.to_string idx))
         | _ -> raise (RuntimeError "Invalid arguments to json_set"))

   | "json_has" ->
       (* (json_has node key) — single key membership.
          (json_has node ["a" 0 "b"]) — array-of-keys; safe walk, returns false
          on any missing segment instead of raising. *)
       (match arg_vals with
        | [node; VArray keys] ->
            (try let _ = json_walk_keys node !keys in VBool true
             with RuntimeError _ -> VBool false)
        | [VMap (m, _); VString k] -> VBool (Hashtbl.mem m k)
        | _ -> raise (RuntimeError "Invalid arguments to json_has"))

   | "json_delete" ->
       (* (json_delete node ["a" "b"]) walks to parent then removes leaf key.
          Map parents only — array element deletion would shift indices. *)
       (match arg_vals with
        | [root; VArray keys] ->
            let ks = !keys in
            if Array.length ks = 0 then
              raise (RuntimeError "json_delete: empty key array")
            else begin
              let (parent, last) = json_walk_parent root ks in
              (match parent, last with
               | VMap (m, ks_ref), VString k -> vmap_delete m ks_ref k
               | _ -> raise (RuntimeError "json_delete: parent must be map and final segment a string"));
              root
            end
        | [VMap (m, keys); VString k] ->
            vmap_delete m keys k;
            VMap (m, keys)
        | _ -> raise (RuntimeError "Invalid arguments to json_delete"))

   | "json_push" ->
       (match arg_vals with
        | [VArray arr; v] ->
            arr := Array.append !arr [|v|];
            VArray arr
        | _ -> raise (RuntimeError "Invalid arguments to json_push"))

   | "json_length" ->
       (match arg_vals with
        | [VArray arr] -> VInt (Int64.of_int (Array.length !arr))
        | [VMap (m, _)] -> VInt (Int64.of_int (Hashtbl.length m))
        | _ -> raise (RuntimeError "Invalid arguments to json_length"))

   | "json_type" ->
       (match arg_vals with
        | [VMap _] -> VString "object"
        | [VArray _] -> VString "array"
        | [VString _] -> VString "string"
        | [VInt _] -> VString "number"
        | [VFloat _] -> VString "number"
        | [VBool _] -> VString "boolean"
        | [VUnit] -> VString "null"
        | _ -> VString "unknown")

   (* Map operations - additional *)
   | "map_length" ->
       (match arg_vals with
        | [VMap (m, _)] -> VInt (Int64.of_int (Hashtbl.length m))
        | _ -> raise (RuntimeError "Invalid arguments to map_length"))

   | "map_values" ->
       (match arg_vals with
        | [VMap (m, keys)] ->
            let values = List.filter_map (fun k -> Hashtbl.find_opt m k) !keys in
            VArray (ref (Array.of_list values))
        | _ -> raise (RuntimeError "Invalid arguments to map_values"))

   (* Additional type conversions *)
   | "cast_float_decimal" ->
       (match arg_vals with
        | [VFloat f] -> VDecimal (format_decimal f)
        | _ -> raise (RuntimeError "Invalid arguments to cast_float_decimal"))

   | "cast_decimal_float" ->
       (match arg_vals with
        | [VDecimal s] -> VFloat (float_of_string s)
        | _ -> raise (RuntimeError "Invalid arguments to cast_decimal_float"))

   (* char_from_code: convert integer char code to single-character string *)
   | "char_from_code" ->
       (match arg_vals with
        | [VInt n] -> VString (String.make 1 (Char.chr (Int64.to_int n)))
        | _ -> raise (RuntimeError "Invalid arguments to char_from_code"))

   (* Array additional ops *)
   | "array_pop" ->
       (match arg_vals with
        | [VArray arr] ->
            let len = Array.length !arr in
            if len = 0 then VUnit
            else begin
              let last = !arr.(len - 1) in
              arr := Array.sub !arr 0 (len - 1);
              last
            end
        | _ -> raise (RuntimeError "Invalid arguments to array_pop"))

   | "array_remove" ->
       (match arg_vals with
        | [VArray arr; VInt idx] ->
            let i = Int64.to_int idx in
            let len = Array.length !arr in
            if i >= 0 && i < len then begin
              let new_arr = Array.concat [
                Array.sub !arr 0 i;
                Array.sub !arr (i + 1) (len - i - 1)
              ] in
              arr := new_arr;
              VArray arr
            end else
              VArray arr
        | _ -> raise (RuntimeError "Invalid arguments to array_remove"))

   | "array_slice" ->
       (match arg_vals with
        | [VArray arr; VInt start; VInt len] ->
            let s = Int64.to_int start in
            let l = Int64.to_int len in
            let arr_len = Array.length !arr in
            let s = max 0 s in
            let l = min l (arr_len - s) in
            if l <= 0 then VArray (ref [||])
            else VArray (ref (Array.sub !arr s l))
        | _ -> raise (RuntimeError "Invalid arguments to array_slice"))

   | "array_concat" ->
       (match arg_vals with
        | [VArray a; VArray b] ->
            VArray (ref (Array.append !a !b))
        | _ -> raise (RuntimeError "Invalid arguments to array_concat"))

   (* file_append *)
   | "file_append" ->
       (match arg_vals with
        | [VString path; VString content] ->
            (try
              let fd = Unix.openfile path [Unix.O_WRONLY; Unix.O_CREAT; Unix.O_APPEND] 0o644 in
              let _ = Unix.write fd (Bytes.of_string content) 0 (String.length content) in
              Unix.close fd;
              VBool true
            with Unix.Unix_error _ ->
              raise (RuntimeError ("Could not append to file: " ^ path)))
        | _ -> raise (RuntimeError "Invalid arguments to file_append"))

   (* tcp_receive with single arg - default 4096 buffer *)
   | "tcp_tls_connect" ->
       (match arg_vals with
        | [VString host; VInt port] ->
            Ssl.init ();
            let ctx = Ssl.create_context Ssl.TLSv1_2 Ssl.Client_context in
            ignore (Ssl.set_default_verify_paths ctx);
            let host_addr = (Unix.gethostbyname host).Unix.h_addr_list.(0) in
            let sockaddr = Unix.ADDR_INET (host_addr, Int64.to_int port) in
            let sock = Unix.socket Unix.PF_INET Unix.SOCK_STREAM 0 in
            Unix.connect sock sockaddr;
            let ssl_sock = Ssl.embed_socket sock ctx in
            Ssl.set_client_SNI_hostname ssl_sock host;
            Ssl.connect ssl_sock;
            VTlsSocket ssl_sock
        | _ -> raise (RuntimeError "Invalid arguments to tcp_tls_connect"))

   (* Type checking *)
   | "type_of" ->
       (match arg_vals with
        | [VInt _] -> VString "int"
        | [VFloat _] -> VString "float"
        | [VDecimal _] -> VString "decimal"
        | [VString _] -> VString "string"
        | [VBool _] -> VString "bool"
        | [VArray _] -> VString "array"
        | [VMap _] -> VString "map"
        | [VUnit] -> VString "unit"
        | [VFunction _] -> VString "function"
        | _ -> VString "unknown")

   | "is_array" ->
       (match arg_vals with
        | [VArray _] -> VBool true
        | _ -> VBool false)

   | "is_object" ->
       (match arg_vals with
        | [VMap _] -> VBool true
        | _ -> VBool false)

   (* Environment *)
   | "getenv" ->
       (match arg_vals with
        | [VString name] ->
            VString (try Sys.getenv name with Not_found -> "")
        | _ -> raise (RuntimeError "Invalid arguments to getenv"))

   | "exit" ->
       (match arg_vals with
        | [VInt code] -> exit (Int64.to_int code)
        | _ -> raise (RuntimeError "Invalid arguments to exit"))

   (* WebSocket operations *)
   | "ws_accept" ->
       (match arg_vals with
        | [VSocket client_fd] ->
            let transport = WsPlain client_fd in
            ws_server_handshake transport;
            VWsSocket transport
        | [VTlsSocket ssl_sock] ->
            let transport = WsTls ssl_sock in
            ws_server_handshake transport;
            VWsSocket transport
        | _ -> raise (RuntimeError "Invalid arguments to ws_accept"))

   | "ws_connect" ->
       (match arg_vals with
        | [VString host; VInt port; VString path] ->
            let sock = Unix.socket Unix.PF_INET Unix.SOCK_STREAM 0 in
            let host_addr = (Unix.gethostbyname host).Unix.h_addr_list.(0) in
            Unix.connect sock (Unix.ADDR_INET (host_addr, Int64.to_int port));
            let transport = WsPlain sock in
            ws_client_handshake transport host path;
            VWsSocket transport
        | _ -> raise (RuntimeError "Invalid arguments to ws_connect"))

   | "ws_send" ->
       (match arg_vals with
        | [VWsSocket transport; VString msg] ->
            let frame = ws_encode_frame msg in
            ws_write transport frame;
            VUnit
        | _ -> raise (RuntimeError "Invalid arguments to ws_send"))

   | "ws_receive" ->
       (match arg_vals with
        | [VWsSocket transport] ->
            let rec read_until_text () =
              let (opcode, payload) = ws_decode_frame transport in
              match opcode with
              | 1 -> VString payload  (* text frame *)
              | 8 -> VString ""       (* close frame *)
              | 9 ->                  (* ping - send pong *)
                  let pong = Buffer.create (String.length payload + 2) in
                  Buffer.add_char pong (Char.chr 0x8A);  (* FIN + pong opcode *)
                  Buffer.add_char pong (Char.chr (String.length payload));
                  Buffer.add_string pong payload;
                  ws_write transport (Buffer.contents pong);
                  read_until_text ()
              | 10 -> read_until_text ()  (* pong - ignore *)
              | _ -> read_until_text ()   (* skip unknown *)
            in
            read_until_text ()
        | _ -> raise (RuntimeError "Invalid arguments to ws_receive"))

   | "ws_close" ->
       (match arg_vals with
        | [VWsSocket transport] ->
            (try ws_send_close transport ~masked:false with _ -> ());
            (match transport with
             | WsPlain fd -> (try Unix.close fd with _ -> ())
             | WsTls ssl -> (try Ssl.shutdown ssl with _ -> ()));
            VUnit
        | _ -> raise (RuntimeError "Invalid arguments to ws_close"))

   (* User-defined functions *)
   | _ ->
       (try
         let func_val = env_get env func_name in
         match func_val with
         | VFunction (_name, params, _ret_type, body) ->
             let func_env = env_create () in
             (* Copy all functions from parent env to func_env *)
             Hashtbl.iter (fun k v ->
               match v with
               | VFunction _ -> env_set func_env k v
               | _ -> ()
             ) env;
             (* Add local parameters *)
             List.iter2 (fun param arg_val ->
               env_set func_env param.param_name arg_val
             ) params arg_vals;
             (try
               let last_result = eval_block func_env body in
               (* main: implicit (ret 0); other functions: implicit return of last expression value *)
               if func_name = "main" then VInt 0L else last_result
             with Return v -> v)
          | _ -> raise (RuntimeError (func_name ^ " is not a function"))
        with Not_found ->
          raise (RuntimeError ("Unknown function: " ^ func_name)))

(* Execute tests *)
and execute_tests env tests =
  let passed = ref 0 in
  let failed = ref 0 in
  List.iter (fun test ->
    Printf.printf "Test: %s\n" test.test_func_name;
    List.iter (fun case ->
      let func_env = env_create () in
      try
        let func_val = env_get env test.test_func_name in
        match func_val with
         | VFunction (_name, params, _ret_type, body) ->
             (* Copy all functions from parent env to func_env *)
             Hashtbl.iter (fun k v ->
               match v with
               | VFunction _ -> env_set func_env k v
               | _ -> ()
             ) env;
             let arg_vals = List.map (eval env) case.test_inputs in
             List.iter2 (fun param arg_val ->
               env_set func_env param.param_name arg_val
             ) params arg_vals;
            let result =
              try eval_block func_env body
              with Return v -> v
            in
             let expected = eval env case.test_expected in
             if values_equal result expected then (
               Printf.printf "  ✓ %s\n" case.test_description;
               incr passed
             ) else (
               Printf.printf "  ✗ %s\n" case.test_description;
               Printf.printf "    Expected: %s\n" (string_of_value expected);
               Printf.printf "    Got: %s\n" (string_of_value result);
               incr failed
             )
        | _ -> ()
      with e ->
        Printf.printf "  ✗ %s (Error: %s)\n" case.test_description (Printexc.to_string e);
        incr failed
    ) test.test_cases
  ) tests;
  Printf.printf "\n%d passed, %d failed\n" !passed !failed;
  if !failed > 0 then 1 else 0

(* Execute module *)

(* Find project root by walking up from a starting directory looking for stdlib/ *)
let find_project_root start_dir =
  let rec walk dir =
    let stdlib_dir = Filename.concat dir "stdlib" in
    if Sys.file_exists stdlib_dir && Sys.is_directory stdlib_dir then
      Some dir
    else
      let parent = Filename.dirname dir in
      if parent = dir then None  (* reached filesystem root *)
      else walk parent
  in
  walk start_dir

(* Mutable reference to the source file path, set by VM entry point *)
let source_file_path = ref ""

(* Diagnostic flags (output_emitted, diagnose_enabled) are forward-declared
   at the top of this file so print/println and (argv) can reference them
   before this point. Diagnostics are ON by default; set SIGIL_DIAGNOSE=0
   to silence (used in batch test runs that assert on stderr). *)

let compute_stdlib_paths () =
  let subdirs = ["stdlib/core/"; "stdlib/data/"; "stdlib/net/";
                 "stdlib/sys/"; "stdlib/crypto/"; "stdlib/pattern/";
                 "stdlib/db/"] in
  let make_paths root =
    List.map (fun sub -> Filename.concat root sub) subdirs
  in
  (* Strategy 1: relative to source file *)
  let from_source =
    if !source_file_path <> "" then
      let source_dir = Filename.dirname (if Filename.is_relative !source_file_path
        then Filename.concat (Sys.getcwd ()) !source_file_path
        else !source_file_path) in
      match find_project_root source_dir with
      | Some root -> make_paths root
      | None -> []
    else []
  in
  (* Strategy 2: relative to executable *)
  let from_exe =
    let exe_dir = Filename.dirname Sys.executable_name in
    let exe_abs = if Filename.is_relative exe_dir
      then Filename.concat (Sys.getcwd ()) exe_dir
      else exe_dir in
    match find_project_root exe_abs with
    | Some root -> make_paths root
    | None -> []
  in
  (* Strategy 3: relative to cwd *)
  let from_cwd =
    match find_project_root (Sys.getcwd ()) with
    | Some root -> make_paths root
    | None -> []
  in
  (* Deduplicate while preserving order *)
  let seen = Hashtbl.create 16 in
  List.filter (fun p ->
    if Hashtbl.mem seen p then false
    else (Hashtbl.replace seen p (); true)
  ) (from_source @ from_exe @ from_cwd)

(* Load a module from stdlib *)
let load_module module_name =
  let search_paths = compute_stdlib_paths () in
  let found_path = ref None in
  List.iter (fun base_path ->
    let file_path = base_path ^ module_name ^ ".sigil" in
    if Sys.file_exists file_path then begin
      found_path := Some file_path
    end
  ) search_paths;
  match !found_path with
  | None -> None
  | Some file_path ->
      try
        (* Read and parse the module file *)
        let ic = open_in file_path in
        let content = really_input_string ic (in_channel_length ic) in
        close_in ic;
        let tokens = Lexer.tokenize content in
        let module_def = Parser.parse tokens in
        Some module_def
      with _ -> None

(* Register all functions from a module into the environment *)
let register_module env module_def =
  List.iter (fun func ->
    let func_val = VFunction (
      func.func_name,
      func.func_params,
      func.func_return_type,
      func.func_body
    ) in
    env_set env func.func_name func_val
  ) module_def.module_functions

(* Load and register all imported modules *)
let rec load_imports env imports =
  List.iter (fun module_name ->
    match load_module module_name with
    | Some module_def ->
        register_module env module_def;
        (* Also load any imports from the imported module *)
        load_imports env module_def.module_imports
    | None ->
        Printf.eprintf "WARNING: Could not load import: %s\n" module_name
  ) imports

(* Execute module *)
let rec execute_module module_def =
   let global_env = env_create () in

   (* Auto-load the core prelude so its functions (tokens, squeeze,
      split_blocks, find_all, ...) are available with zero import.
      The prelude is the layer for pure compositions over primitive
      builtins — anything that COULD be written in Sigil belongs there
      rather than in OCaml. User imports and user functions can still
      shadow prelude names. *)
   (match load_module "prelude" with
    | Some prelude_def ->
        register_module global_env prelude_def;
        load_imports global_env prelude_def.module_imports
    | None -> ());

   (* Load and register imported modules first *)
   load_imports global_env module_def.module_imports;

   (* Register all functions from main module *)
   List.iter (fun func ->
     let func_val = VFunction (
       func.func_name,
       func.func_params,
       func.func_return_type,
       func.func_body
     ) in
     env_set global_env func.func_name func_val
   ) module_def.module_functions;

   (* Execute tests if present, otherwise execute main.
      In test mode we mark output_emitted=true unconditionally — the
      test framework writes its own "Test: ..." headers via Printf.printf
      which doesn't go through the print/println builtins. Without this,
      the no-output-produced diagnostic would fire on every clean test
      run, which is a false positive. *)
   if List.length module_def.module_tests > 0 then begin
     output_emitted := true;
     execute_tests global_env module_def.module_tests
   end
   else
     execute_main global_env module_def.module_functions

and execute_main env functions =
  try
    let _main_func = List.find (fun f -> f.func_name = "main") functions in
    let result = eval_call env "main" [] in
    match result with
    | VInt n -> Int64.to_int n
    | _ -> 0
  with Not_found ->
    Printf.eprintf "Error: No 'main' function found\n";
    1
