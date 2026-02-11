(* S-Expression Parser for AISL *)

open Lexer
open Types
open Ast

exception ParseError of string

type parser_state = {
  tokens : token list;
  pos : int;
}

let peek state =
  if state.pos >= List.length state.tokens then EOF
  else List.nth state.tokens state.pos

let advance state =
  { state with pos = state.pos + 1 }

let expect_token expected_tok state =
  let tok = peek state in
  if tok = expected_tok then advance state
  else raise (ParseError ("Expected " ^ string_of_token expected_tok ^ " but got " ^ string_of_token tok))

let expect_symbol state =
  match peek state with
  | Symbol s -> (s, advance state)
  | tok -> raise (ParseError ("Expected symbol but got " ^ string_of_token tok))

(* Parse type annotations *)
let parse_type state =
  match peek state with
  | Symbol "int" -> (TInt, advance state)
  | Symbol "float" -> (TFloat, advance state)
  | Symbol "decimal" -> (TDecimal, advance state)
  | Symbol "string" -> (TString, advance state)
  | Symbol "bool" -> (TBool, advance state)
  | Symbol "unit" -> (TUnit, advance state)
  | Symbol "array" -> (TArray TUnit, advance state)  (* Simplified - no type params yet *)
  | Symbol "map" -> (TMap (TUnit, TUnit), advance state)  (* Simplified *)
  | Symbol "json" -> (TJson, advance state)
  | Symbol "regex" -> (TRegex, advance state)
  | Symbol "process" -> (TProcess, advance state)
  | Symbol "socket" -> (TSocket, advance state)
  | Symbol "channel" -> (TSocket, advance state)  (* channel maps to TSocket for now *)
  | tok -> raise (ParseError ("Expected type but got " ^ string_of_token tok))

(* Reserved type keywords that cannot be used as variable names *)
let type_keywords = [
  "int"; "float"; "decimal"; "string"; "bool"; "unit";
  "array"; "map"; "json"; "regex"; "process"; "socket";
  "channel"
]

let is_type_keyword name = List.mem name type_keywords

let check_not_type_keyword name context =
  if is_type_keyword name then
    raise (ParseError (
      "Cannot use type keyword '" ^ name ^ "' as " ^ context ^
      ". Use a descriptive name instead (e.g., '" ^ name ^ "_data', '" ^ name ^ "_value')"))

(* Parse expressions *)
let rec parse_expr state =
  match peek state with
  | IntLit n -> (LitInt n, advance state)
  | FloatLit f -> (LitFloat f, advance state)
  | DecimalLit s -> (LitDecimal s, advance state)
  | StringLit s -> (LitString s, advance state)
  | BoolLit b -> (LitBool b, advance state)
  | Symbol s -> (Var s, advance state)
  | LParen -> parse_sexpr state
  | LBracket -> parse_array_literal state
  | LBrace -> parse_map_literal state
  | tok -> raise (ParseError ("Expected expression but got " ^ string_of_token tok))

and parse_sexpr state =
  let state = expect_token LParen state in
  let (sym, state) = expect_symbol state in
  match sym with
  | "set" -> parse_set state
  | "ret" | "return" -> parse_return state
  | "if" -> parse_if state
  | "while" -> parse_while state
  | "loop" -> parse_loop state
  | "for-each" -> parse_foreach state
  | "and" -> parse_and state
  | "or" -> parse_or state
  | "break" -> (Break, expect_token RParen state)
  | "continue" -> (Continue, expect_token RParen state)
  | "label" -> parse_label state
  | "goto" -> parse_goto state
  | "ifnot" -> parse_ifnot state
  | "try" -> parse_try state
  | "cond" -> parse_cond state
  | _ -> parse_call sym state

and parse_set state =
  let (var_name, state) = expect_symbol state in
  check_not_type_keyword var_name "variable name";
  let (var_type, state) = parse_type state in
  let (value_expr, state) = parse_expr state in
  let state = expect_token RParen state in
  (Set (var_name, var_type, value_expr), state)

and parse_return state =
  let (expr, state) = parse_expr state in
  let state = expect_token RParen state in
  (Return expr, state)

and parse_if state =
  let (cond, state) = parse_expr state in
  (* Collect all body expressions *)
  let (all_body, state) = parse_body_until_rparen state [] in
  (* Check if the last expression is an (else ...) block *)
  let has_else_block exprs =
    match exprs with
    | [] -> ([], None)
    | [Call ("else", _)] ->
        (* This shouldn't happen via normal parsing - else is handled below *)
        ([], None)
    | _ ->
        (* Scan for an else block: look for the pattern where we have
           expressions and the last group starts with else *)
        (exprs, None)
  in
  (* Re-parse: we need to detect (else ...) during body parsing.
     The trick: if any body expr is a Call("else", args), it's actually
     the else branch. But "else" gets parsed as a function call.
     We split: everything before the else-call is then-body,
     the else-call's args are the else-body. *)
  let rec split_else acc = function
    | [] -> (List.rev acc, None)
    | Call ("else", else_args) :: rest ->
        (* Everything after else should be empty since else is last *)
        if rest <> [] then
          raise (ParseError "else block must be the last item in an if expression");
        (List.rev acc, Some else_args)
    | expr :: rest -> split_else (expr :: acc) rest
  in
  let (then_body, else_body) = split_else [] all_body in
  let _ = has_else_block in  (* suppress warning *)
  (If (cond, then_body, else_body), state)

and parse_while state =
  let (cond, state) = parse_expr state in
  let (body, state) = parse_body_until_rparen state [] in
  (While (cond, body), state)

and parse_loop state =
  let (body, state) = parse_body_until_rparen state [] in
  (Loop body, state)

and parse_foreach state =
  let (var_name, state) = expect_symbol state in
  check_not_type_keyword var_name "for-each variable name";
  let (var_type, state) = parse_type state in
  let (collection_expr, state) = parse_expr state in
  let (body, state) = parse_body_until_rparen state [] in
  (ForEach (var_name, var_type, collection_expr, body), state)

and parse_and state =
  let (left, state) = parse_expr state in
  let (right, state) = parse_expr state in
  let state = expect_token RParen state in
  (And (left, right), state)

and parse_or state =
  let (left, state) = parse_expr state in
  let (right, state) = parse_expr state in
  let state = expect_token RParen state in
  (Or (left, right), state)

and parse_label state =
  let (label_name, state) = expect_symbol state in
  let state = expect_token RParen state in
  (Label label_name, state)

and parse_goto state =
  let (label_name, state) = expect_symbol state in
  let state = expect_token RParen state in
  (Goto label_name, state)

and parse_ifnot state =
  let (cond, state) = parse_expr state in
  let (label_name, state) = expect_symbol state in
  let state = expect_token RParen state in
  (IfNot (cond, label_name), state)

and parse_try state =
  (* Parse body expressions until we hit (catch ...) *)
  let rec parse_try_body state acc =
    match peek state with
    | RParen ->
        (* No catch block found - error *)
        raise (ParseError "try block requires a (catch ...) clause")
    | LParen ->
        (* Check if this is (catch ...) *)
        let tok_at_pos_plus_1 =
          if state.pos + 1 < List.length state.tokens then
            Some (List.nth state.tokens (state.pos + 1))
          else None
        in
        (match tok_at_pos_plus_1 with
         | Some (Symbol "catch") ->
             (* Parse catch block *)
             let state = expect_token LParen state in
             let state = expect_token (Symbol "catch") state in
             let (catch_var, state) = expect_symbol state in
             check_not_type_keyword catch_var "catch variable name";
             let (catch_type, state) = parse_type state in
             let (catch_body, state) = parse_body_until_rparen state [] in
             let state = expect_token RParen state in  (* close the try *)
             (List.rev acc, catch_var, catch_type, catch_body, state)
         | _ ->
             let (expr, state) = parse_expr state in
             parse_try_body state (expr :: acc))
    | _ ->
        let (expr, state) = parse_expr state in
        parse_try_body state (expr :: acc)
  in
   let (try_body, catch_var, catch_type, catch_body, state) = parse_try_body state [] in
  (Try (try_body, catch_var, catch_type, catch_body), state)

and parse_cond state =
  (* Parse branches: each is (condition body...) *)
  let rec parse_branches state acc =
    match peek state with
    | RParen -> (List.rev acc, expect_token RParen state)
    | LParen ->
        let state = expect_token LParen state in
        let (cond, state) = parse_expr state in
        let (body, state) = parse_body_until_rparen state [] in
        parse_branches state ((cond, body) :: acc)
    | tok -> raise (ParseError ("Expected cond branch (condition body...) but got " ^ string_of_token tok))
  in
  let (branches, state) = parse_branches state [] in
  if branches = [] then
    raise (ParseError "cond requires at least one branch");
  (Cond branches, state)

and parse_array_literal state =
  let state = expect_token LBracket state in
  let rec parse_elems state acc =
    match peek state with
    | RBracket -> (List.rev acc, expect_token RBracket state)
    | _ ->
        let (expr, state) = parse_expr state in
        parse_elems state (expr :: acc)
  in
  let (elems, state) = parse_elems state [] in
  (LitArray elems, state)

and parse_map_literal state =
  let state = expect_token LBrace state in
  let rec parse_pairs state acc =
    match peek state with
    | RBrace -> (List.rev acc, expect_token RBrace state)
    | _ ->
        let (key, state) = parse_expr state in
        let (value, state) = parse_expr state in
        parse_pairs state ((key, value) :: acc)
  in
  let (pairs, state) = parse_pairs state [] in
  (LitMap pairs, state)

and parse_call func_name state =
  let (args, state) = parse_args state [] in
  let state = expect_token RParen state in
  (Call (func_name, args), state)

and parse_args state acc =
  match peek state with
  | RParen -> (List.rev acc, state)
  | _ ->
      let (expr, state) = parse_expr state in
      parse_args state (expr :: acc)

and parse_body_until_rparen state acc =
  match peek state with
  | RParen -> (List.rev acc, expect_token RParen state)
  | _ ->
      let (expr, state) = parse_expr state in
      parse_body_until_rparen state (expr :: acc)

(* Parse function parameters *)
let rec parse_params state acc =
  match peek state with
  | Symbol "->" -> (List.rev acc, state)
  | Symbol _ ->
      let (param_name, state) = expect_symbol state in
      check_not_type_keyword param_name "function parameter name";
      let (param_type, state) = parse_type state in
      let param = { param_name; param_type } in
      parse_params state (param :: acc)
  | tok -> raise (ParseError ("Expected parameter or '->' but got " ^ string_of_token tok))

(* Parse function definition *)
let parse_function state =
  let state = expect_token LParen state in
  let state = expect_token (Symbol "fn") state in
  let (func_name, state) = expect_symbol state in
  
  (* Parse parameters *)
  let (params, state) = parse_params state [] in
  
  (* Parse arrow and return type *)
  let state = expect_token (Symbol "->") state in
  let (return_type, state) = parse_type state in
  
  (* Parse body *)
  let (body, state) = parse_body_until_rparen state [] in
  
  let func_def = { func_name; func_params = params; func_return_type = return_type; func_body = body } in
  (func_def, state)

(* Parse import *)
let parse_import state =
  let state = expect_token LParen state in
  let state = expect_token (Symbol "import") state in
  let (module_name, state) = expect_symbol state in
  let state = expect_token RParen state in
  (module_name, state)

(* Parse test-spec *)
let skip_sexp state =
  match peek state with
  | LParen ->
      let state = advance state in
      let rec skip_inner state depth =
        match peek state with
        | RParen -> if depth = 0 then advance state else skip_inner (advance state) (depth - 1)
        | LParen -> skip_inner (advance state) (depth + 1)
        | EOF -> state
        | _ -> skip_inner (advance state) depth
      in
      skip_inner state 0
  | _ -> advance state

let parse_test_case state =
  let state = expect_token LParen state in
  let state = expect_token (Symbol "case") state in
  
  (* Description *)
  let (desc, state) = match peek state with
    | StringLit s -> (s, advance state)
    | tok -> raise (ParseError ("Expected test description string but got " ^ string_of_token tok))
  in
  
  (* Skip optional (mock ...) clauses *)
  let rec skip_mocks state =
    match peek state with
    | LParen ->
        let tok_at_pos_plus_1 = 
          if state.pos + 1 < List.length state.tokens then
            Some (List.nth state.tokens (state.pos + 1))
          else None
        in
        (match tok_at_pos_plus_1 with
         | Some (Symbol "mock") -> skip_mocks (skip_sexp state)
         | _ -> state)
    | _ -> state
  in
  let state = skip_mocks state in
  
  (* Input *)
  let state = expect_token LParen state in
  let state = expect_token (Symbol "input") state in
  let (inputs, state) = parse_args state [] in
  let state = expect_token RParen state in
  
  (* Expected *)
  let state = expect_token LParen state in
  let state = expect_token (Symbol "expect") state in
  let (expected, state) = parse_expr state in
  let state = expect_token RParen state in
  
  let state = expect_token RParen state in
  ({ test_description = desc; test_inputs = inputs; test_expected = expected }, state)

let rec parse_test_cases state acc =
  match peek state with
  | LParen ->
      let tok_at_pos_plus_1 = 
        if state.pos + 1 < List.length state.tokens then
          Some (List.nth state.tokens (state.pos + 1))
        else None
      in
      (match tok_at_pos_plus_1 with
       | Some (Symbol "case") ->
           let (test_case, state) = parse_test_case state in
           parse_test_cases state (test_case :: acc)
       | _ -> (List.rev acc, state))
  | _ -> (List.rev acc, state)

let parse_test_spec state =
  let state = expect_token LParen state in
  let state = expect_token (Symbol "test-spec") state in
  let (func_name, state) = expect_symbol state in
  let (test_cases, state) = parse_test_cases state [] in
  let state = expect_token RParen state in
  ({ test_func_name = func_name; test_cases }, state)

(* Parse module *)
let parse_module state =
  let state = expect_token LParen state in
  let state = expect_token (Symbol "module") state in
  let (module_name, state) = expect_symbol state in
  
  let rec parse_items state imports functions tests note =
    match peek state with
    | RParen -> 
        let _state = expect_token RParen state in
        { module_name; module_imports = List.rev imports;
          module_functions = List.rev functions;
          module_tests = List.rev tests;
          module_note = note }
    | EOF ->
        { module_name; module_imports = List.rev imports;
          module_functions = List.rev functions;
          module_tests = List.rev tests;
          module_note = note }
    | LParen ->
        let tok_at_pos_plus_1 = 
          if state.pos + 1 < List.length state.tokens then
            Some (List.nth state.tokens (state.pos + 1))
          else None
        in
        (match tok_at_pos_plus_1 with
         | Some (Symbol "import") ->
             let (imp, state) = parse_import state in
             parse_items state (imp :: imports) functions tests note
         | Some (Symbol "fn") ->
             let (func, state) = parse_function state in
             parse_items state imports (func :: functions) tests note
         | Some (Symbol "test-spec") ->
             let (test, state) = parse_test_spec state in
             parse_items state imports functions (test :: tests) note
         | Some (Symbol "meta-note") ->
             let state = expect_token LParen state in
             let state = expect_token (Symbol "meta-note") state in
             let (note_text, state) = match peek state with
               | StringLit s -> (s, advance state)
               | tok -> raise (ParseError ("Expected note string but got " ^ string_of_token tok))
             in
             let state = expect_token RParen state in
             parse_items state imports functions tests (Some note_text)
         | _ -> raise (ParseError ("Expected module item but got " ^ 
                 (match tok_at_pos_plus_1 with Some tok -> string_of_token tok | None -> "EOF"))))
    | tok -> raise (ParseError ("Expected module item or ) but got " ^ string_of_token tok))
  in
  parse_items state [] [] [] None

let parse tokens =
  let state = { tokens; pos = 0 } in
  parse_module state
