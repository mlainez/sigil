(* Sigil VM Runner *)

open Lexer
open Parser
open Interpreter

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
    Printf.eprintf "Usage: %s <file.sigil>\n" Sys.argv.(0);
    exit 1
  end;

  let filename = Sys.argv.(1) in
  let exit_code = run_file filename in
  exit exit_code
