(* AISL Tree-Walking Interpreter *)

open Types
open Ast
open Lexer
open Parser
open Unix

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
  | VSocket _ -> "socket" | VTlsSocket _ -> "socket" | VWsSocket _ -> "socket"
  | VChannel _ -> "socket" | VProcess _ -> "process"

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
  let ws_key = base64_encode "aisl-ws-key-0000" in
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
  | VFloat f -> string_of_float f
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

   | Var name -> env_get env name
  
  | Call (func_name, args) ->
      eval_call env func_name args
  
  | Set (var_name, var_type, value_expr) ->
      let value = eval env value_expr in
      if not (type_matches var_type value) then
        raise (RuntimeError (
          "Type mismatch: variable '" ^ var_name ^
          "' declared as " ^ string_of_type_kind var_type ^
          " but got " ^ string_of_value_type value))
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

  | ForEach (var_name, var_type, collection_expr, body) ->
      let coll = eval env collection_expr in
      (match coll with
       | VArray arr ->
           let len = Array.length !arr in
           let i = ref 0 in
           (try
             while !i < len do
               let elem = !arr.(!i) in
               if not (type_matches var_type elem) then
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
       | _ -> raise (RuntimeError "for-each requires an array or map"))

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

 and eval_call env func_name args =
  let arg_vals = List.map (eval env) args in

  match func_name with
  (* Arithmetic - int *)
   | "add" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.add a b)
        | [VFloat a; VFloat b] -> VFloat (a +. b)
        | [VDecimal a; VDecimal b] ->
             VDecimal (bigdecimal_add a b)
         | _ -> raise (RuntimeError ("Invalid arguments to add")))

   | "sub" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.sub a b)
        | [VFloat a; VFloat b] -> VFloat (a -. b)
        | [VDecimal a; VDecimal b] ->
             VDecimal (bigdecimal_sub a b)
         | _ -> raise (RuntimeError "Invalid arguments to sub"))

   | "mul" ->
       (match arg_vals with
        | [VInt a; VInt b] -> VInt (Int64.mul a b)
        | [VFloat a; VFloat b] -> VFloat (a *. b)
        | [VDecimal a; VDecimal b] ->
             VDecimal (bigdecimal_mul a b)
         | _ -> raise (RuntimeError "Invalid arguments to mul"))

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
         | _ -> raise (RuntimeError "Invalid arguments to div"))
  
  | "mod" ->
      (match arg_vals with
       | [VInt a; VInt b] ->
           if b = 0L then raise (RuntimeError "Division by zero")
           else VInt (Int64.rem a b)
       | _ -> raise (RuntimeError "Invalid arguments to mod"))
  
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
        | _ -> raise (RuntimeError "Invalid arguments to abs"))

  | "min" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VInt (if a < b then a else b)
       | [VFloat a; VFloat b] -> VFloat (min a b)
       | [VDecimal a; VDecimal b] ->
            if bigdecimal_compare a b <= 0 then VDecimal (decimal_normalize a) else VDecimal (decimal_normalize b)
        | _ -> raise (RuntimeError "Invalid arguments to min"))

  | "max" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VInt (if a > b then a else b)
       | [VFloat a; VFloat b] -> VFloat (max a b)
       | [VDecimal a; VDecimal b] ->
            if bigdecimal_compare a b >= 0 then VDecimal (decimal_normalize a) else VDecimal (decimal_normalize b)
        | _ -> raise (RuntimeError "Invalid arguments to max"))

  | "sqrt" ->
      (match arg_vals with
       | [VFloat a] -> VFloat (sqrt a)
       | _ -> raise (RuntimeError "Invalid arguments to sqrt"))

   | "pow" ->
      (match arg_vals with
       | [VFloat a; VFloat b] -> VFloat (a ** b)
       | _ -> raise (RuntimeError "Invalid arguments to pow"))

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
         | _ -> raise (RuntimeError "Invalid arguments to eq"))
  
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
         | _ -> raise (RuntimeError "Invalid arguments to ne"))
  
  | "lt" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a < b)
       | [VFloat a; VFloat b] -> VBool (a < b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b < 0)
       | _ -> raise (RuntimeError "Invalid arguments to lt"))
  
  | "gt" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a > b)
       | [VFloat a; VFloat b] -> VBool (a > b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b > 0)
       | _ -> raise (RuntimeError "Invalid arguments to gt"))
  
  | "le" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a <= b)
       | [VFloat a; VFloat b] -> VBool (a <= b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b <= 0)
       | _ -> raise (RuntimeError "Invalid arguments to le"))
  
  | "ge" ->
      (match arg_vals with
       | [VInt a; VInt b] -> VBool (a >= b)
       | [VFloat a; VFloat b] -> VBool (a >= b)
       | [VDecimal a; VDecimal b] -> VBool (bigdecimal_compare a b >= 0)
       | _ -> raise (RuntimeError "Invalid arguments to ge"))

  (* Logical operations *)
  | "not" ->
      (match arg_vals with
       | [VBool a] -> VBool (not a)
       | _ -> raise (RuntimeError "Invalid arguments to not"))

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
           let i = Int64.to_int idx in
           if i >= 0 && i < Array.length !arr then
             !arr.(i)
           else
             raise (RuntimeError ("Array index out of bounds: " ^ Int64.to_string idx))
       | _ -> raise (RuntimeError "Invalid arguments to array_get"))

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

   | "array_reverse" ->
       (match arg_vals with
        | [VArray arr] ->
            let len = Array.length !arr in
            let reversed = Array.init len (fun i -> !arr.(len - 1 - i)) in
            arr := reversed;
            VArray arr
        | _ -> raise (RuntimeError "Invalid arguments to array_reverse"))

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
       VArray (ref (Array.of_list (List.map (fun s -> VString s) script_args)))

   | "argv_count" ->
       let count = max 0 (Array.length Sys.argv - 2) in
       VInt (Int64.of_int count)

   (* I/O *)
   | "print" ->
       (match arg_vals with
        | [v] -> print_string (string_of_value v); VUnit
        | _ -> raise (RuntimeError "print takes 1 argument"))
  
  | "println" ->
      (match arg_vals with
       | [v] -> print_endline (string_of_value v); VUnit
       | _ -> raise (RuntimeError "println takes 1 argument"))

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

  (* Regex operations - using OCaml Str library *)
  | "regex_compile" ->
      (match arg_vals with
       | [VString pattern] -> VString pattern  (* Store pattern as string for Str *)
       | _ -> raise (RuntimeError "Invalid arguments to regex_compile"))

  | "regex_match" ->
      (match arg_vals with
       | [VString pattern; VString text] ->
           (try
             let re = Str.regexp pattern in
             let _ = Str.search_forward re text 0 in
             VBool true
           with Not_found -> VBool false
              | _ -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern)))
       | _ -> raise (RuntimeError "Invalid arguments to regex_match"))

  | "regex_find" ->
      (match arg_vals with
       | [VString pattern; VString text] ->
           (try
             let re = Str.regexp pattern in
             let _ = Str.search_forward re text 0 in
             VString (Str.matched_string text)
           with Not_found -> VString ""
              | _ -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern)))
       | _ -> raise (RuntimeError "Invalid arguments to regex_find"))

  | "regex_find_all" ->
      (match arg_vals with
       | [VString pattern; VString text] ->
           (try
             let re = Str.regexp pattern in
             let results = ref [] in
             let pos = ref 0 in
             (try
               while true do
                 let _ = Str.search_forward re text !pos in
                 let matched = Str.matched_string text in
                 results := VString matched :: !results;
                 pos := Str.match_end ();
                 if !pos >= String.length text then raise Not_found
               done
             with Not_found -> ());
             VArray (ref (Array.of_list (List.rev !results)))
           with Failure msg -> raise (RuntimeError ("Invalid regex pattern: " ^ msg))
              | Invalid_argument msg -> raise (RuntimeError ("regex_find_all error: " ^ msg)))
       | _ -> raise (RuntimeError "Invalid arguments to regex_find_all"))

   | "regex_replace" ->
       (match arg_vals with
        | [VString pattern; VString text; VString replacement] ->
            (try
              let re = Str.regexp pattern in
              VString (Str.global_replace re replacement text)
            with _ -> raise (RuntimeError ("Invalid regex pattern: " ^ pattern)))
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
        (match arg_vals with
         | [VMap (m, _); VString k] ->
             (try Hashtbl.find m k
              with Not_found -> raise (RuntimeError ("Key not found in JSON object: " ^ k)))
         | [VArray arr; VInt idx] ->
             let i = Int64.to_int idx in
             if i >= 0 && i < Array.length !arr then !arr.(i)
             else raise (RuntimeError ("JSON array index out of bounds: " ^ Int64.to_string idx))
         | _ -> raise (RuntimeError "Invalid arguments to json_get"))

    | "json_set" ->
        (match arg_vals with
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
       (match arg_vals with
        | [VMap (m, _); VString k] -> VBool (Hashtbl.mem m k)
        | _ -> raise (RuntimeError "Invalid arguments to json_has"))

   | "json_delete" ->
       (match arg_vals with
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
               let _ = eval_block func_env body in
               VUnit
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
              try
                let _ = eval_block func_env body in
                VUnit
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
    let file_path = base_path ^ module_name ^ ".aisl" in
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

   (* Execute tests if present, otherwise execute main *)
   if List.length module_def.module_tests > 0 then
     execute_tests global_env module_def.module_tests
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
