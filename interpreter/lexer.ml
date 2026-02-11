(* S-Expression Lexer for Sigil *)

type token =
  | LParen
  | RParen
  | LBracket
  | RBracket
  | LBrace
  | RBrace
  | Symbol of string
  | IntLit of int64
  | FloatLit of float
  | DecimalLit of string
  | StringLit of string
  | BoolLit of bool
  | EOF

exception LexError of string

let is_whitespace = function
  | ' ' | '\t' | '\n' | '\r' -> true
  | _ -> false

let is_digit = function
  | '0'..'9' -> true
  | _ -> false

let is_alpha = function
  | 'a'..'z' | 'A'..'Z' -> true
  | _ -> false

let is_symbol_char = function
  | 'a'..'z' | 'A'..'Z' | '0'..'9' | '_' | '-' | '+' | '*' | '/' | '<' | '>' | '=' | '!' | '?' -> true
  | _ -> false

let rec skip_whitespace input pos =
  if pos >= String.length input then pos
  else if is_whitespace input.[pos] then skip_whitespace input (pos + 1)
  else pos

let read_string input start_pos =
  let rec loop pos escaped acc =
    if pos >= String.length input then
      raise (LexError "Unterminated string")
    else
      let c = input.[pos] in
      if escaped then
        let c' = match c with
          | 'n' -> '\n'
          | 't' -> '\t'
          | 'r' -> '\r'
          | '\\' -> '\\'
          | '"' -> '"'
          | _ -> c
        in
        loop (pos + 1) false (acc ^ String.make 1 c')
      else if c = '\\' then
        loop (pos + 1) true acc
      else if c = '"' then
        (acc, pos + 1)
      else
        loop (pos + 1) false (acc ^ String.make 1 c)
  in
  loop start_pos false ""

let read_number input start_pos =
  let rec loop pos =
    if pos >= String.length input then pos
    else
      let c = input.[pos] in
      if is_digit c || c = '.' || c = '-' || c = 'e' || c = 'E' then
        loop (pos + 1)
      else
        pos
  in
  let end_pos = loop start_pos in
  let num_str = String.sub input start_pos (end_pos - start_pos) in
  (num_str, end_pos)

let read_symbol input start_pos =
  let rec loop pos =
    if pos >= String.length input then pos
    else if is_symbol_char input.[pos] then loop (pos + 1)
    else pos
  in
  let end_pos = loop start_pos in
  let sym = String.sub input start_pos (end_pos - start_pos) in
  (sym, end_pos)

let tokenize input =
  let rec loop pos acc =
    let pos = skip_whitespace input pos in
    if pos >= String.length input then
      List.rev (EOF :: acc)
    else
      let c = input.[pos] in
      match c with
      | '(' -> loop (pos + 1) (LParen :: acc)
      | ')' -> loop (pos + 1) (RParen :: acc)
      | '[' -> loop (pos + 1) (LBracket :: acc)
      | ']' -> loop (pos + 1) (RBracket :: acc)
      | '{' -> loop (pos + 1) (LBrace :: acc)
      | '}' -> loop (pos + 1) (RBrace :: acc)
      | '"' ->
          let (str, next_pos) = read_string input (pos + 1) in
          loop next_pos (StringLit str :: acc)
      | '-' when pos + 1 < String.length input && is_digit input.[pos + 1] ->
           let (num_str, next_pos) = read_number input pos in
           (* Check for 'd' suffix -> decimal literal *)
           if next_pos < String.length input && input.[next_pos] = 'd' then
             loop (next_pos + 1) (DecimalLit num_str :: acc)
           else
             let tok = 
               if String.contains num_str '.' || String.contains num_str 'e' || String.contains num_str 'E' then
                 FloatLit (float_of_string num_str)
               else
                 IntLit (Int64.of_string num_str)
             in
             loop next_pos (tok :: acc)
       | '0'..'9' ->
           let (num_str, next_pos) = read_number input pos in
           (* Check for 'd' suffix -> decimal literal *)
           if next_pos < String.length input && input.[next_pos] = 'd' then
             loop (next_pos + 1) (DecimalLit num_str :: acc)
           else
             let tok = 
               if String.contains num_str '.' || String.contains num_str 'e' || String.contains num_str 'E' then
                 FloatLit (float_of_string num_str)
               else
                 IntLit (Int64.of_string num_str)
             in
             loop next_pos (tok :: acc)
      | _ when is_alpha c || is_symbol_char c ->
          let (sym, next_pos) = read_symbol input pos in
          let tok = match sym with
            | "true" -> BoolLit true
            | "false" -> BoolLit false
            | _ -> Symbol sym
          in
          loop next_pos (tok :: acc)
      | _ -> raise (LexError ("Unexpected character: " ^ String.make 1 c))
  in
  loop 0 []

let string_of_token = function
  | LParen -> "("
  | RParen -> ")"
  | LBracket -> "["
  | RBracket -> "]"
  | LBrace -> "{"
  | RBrace -> "}"
  | Symbol s -> "Symbol(" ^ s ^ ")"
  | IntLit n -> "Int(" ^ Int64.to_string n ^ ")"
  | FloatLit f -> "Float(" ^ string_of_float f ^ ")"
  | DecimalLit s -> "Decimal(" ^ s ^ "d)"
  | StringLit s -> "String(\"" ^ String.escaped s ^ "\")"
  | BoolLit b -> "Bool(" ^ string_of_bool b ^ ")"
  | EOF -> "EOF"
