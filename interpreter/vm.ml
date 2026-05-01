(* Sigil VM Runner *)

open Lexer
open Parser
open Interpreter

(* --lint mode: a paren-balance scanner that reports actionable errors with
   line:col positions. Designed to give the retry-with-hint pipeline a useful
   message when the local model emits unmatched parens (currently the parser
   reports "Expected expression but got EOF" which doesn't tell the model
   *where* the problem is). *)

(* Walks a source string character-by-character tracking line and column,
   counts paren balance, and returns:
   - Ok ()                  when balanced (string/comment-aware)
   - Error (line, col, msg) on the first imbalance encountered *)
let lint_paren_balance (src : string) : (unit, int * int * string) result =
  let len = String.length src in
  let line = ref 1 and col = ref 1 in
  let openings = ref [] in (* stack of (line, col) of unmatched ( so far *)
  let i = ref 0 in
  let advance () =
    if !i < len then begin
      if src.[!i] = '\n' then begin incr line; col := 1 end
      else incr col;
      incr i
    end
  in
  let result = ref None in
  while !result = None && !i < len do
    let c = src.[!i] in
    (match c with
     | '"' ->
         (* skip a string literal handling backslash-escapes *)
         advance ();
         (try
           while !i < len && src.[!i] <> '"' do
             if src.[!i] = '\\' && !i + 1 < len then begin
               advance (); advance ()
             end else advance ()
           done;
           if !i < len then advance ()  (* consume closing quote *)
           else raise Exit
         with Exit ->
           result := Some (!line, !col, "Unterminated string literal"))
     | ';' when !i + 1 < len && src.[!i + 1] = ';' ->
         (* line comment to end of line *)
         while !i < len && src.[!i] <> '\n' do advance () done
     | '(' ->
         openings := (!line, !col) :: !openings;
         advance ()
     | ')' ->
         (match !openings with
          | _ :: rest -> openings := rest; advance ()
          | [] ->
              result := Some (!line, !col,
                "Extra closing paren at this position — no matching open"))
     | _ -> advance ())
  done;
  (match !result with
   | Some _ -> ()
   | None ->
       (match !openings with
        | [] -> ()
        | (l, c) :: _ ->
            result := Some (l, c,
              Printf.sprintf "Unmatched opening paren at line %d, col %d — \
                              missing a closing `)` to match it" l c)));
  (match !result with
   | None -> Ok ()
   | Some (l, c, m) -> Error (l, c, m))


(* --lint mode: parse-only, returns 0 on success or detailed diagnostic. *)
let lint_file filename =
  try
    let ic = open_in filename in
    let content = really_input_string ic (in_channel_length ic) in
    close_in ic;
    (* Step 1: paren-balance scan with line:col reporting *)
    (match lint_paren_balance content with
     | Error (line, col, msg) ->
         Printf.eprintf "Lint error at line %d, col %d: %s\n" line col msg;
         1
     | Ok () ->
         (* Step 2: full parse (catches non-paren syntax errors) *)
         (try
           let tokens = tokenize content in
           let _ = parse tokens in
           print_endline "OK";
           0
         with
         | LexError msg -> Printf.eprintf "Lex error: %s\n" msg; 1
         | ParseError msg -> Printf.eprintf "Parse error: %s\n" msg; 1
         | e ->
             Printf.eprintf "Unexpected lint error: %s\n"
               (Printexc.to_string e);
             1))
  with Sys_error msg ->
    Printf.eprintf "Error reading file: %s\n" msg;
    1


let run_file filename =
  try
    (* Set source file path for stdlib resolution *)
    Interpreter.source_file_path := filename;

    (* Read the file *)
    let ic = open_in filename in
    let content = really_input_string ic (in_channel_length ic) in
    close_in ic;

    (* Lex and Parse *)
    let tokens = tokenize content in
    let module_def = parse tokens in

    (* Execute *)
    let exit_code = execute_module module_def in
    exit_code
  with
  | Sys_error msg ->
      Printf.eprintf "Error reading file: %s\n" msg;
      1
  | LexError msg ->
      Printf.eprintf "Lexer error: %s\n" msg;
      1
  | ParseError msg ->
      Printf.eprintf "Parse error: %s\n" msg;
      1
  | RuntimeError msg ->
      Printf.eprintf "Runtime error: %s\n" msg;
      1
  | e ->
      Printf.eprintf "Unexpected error: %s\n" (Printexc.to_string e);
      Printexc.print_backtrace stderr;
      1

let () =
  if Array.length Sys.argv < 2 then begin
    Printf.eprintf "Usage: %s [--lint] <file.sigil> [args...]\n" Sys.argv.(0);
    Printf.eprintf "  --lint  Parse-only check with line:col paren diagnostics\n";
    exit 1
  end;

  let exit_code =
    if Sys.argv.(1) = "--lint" then begin
      if Array.length Sys.argv < 3 then begin
        Printf.eprintf "Usage: %s --lint <file.sigil>\n" Sys.argv.(0);
        exit 1
      end;
      lint_file Sys.argv.(2)
    end else
      run_file Sys.argv.(1)
  in
  exit exit_code
