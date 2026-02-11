(* Sigil Abstract Syntax Tree *)

open Types

(* Expressions *)
type expr =
  | LitInt of int64
  | LitFloat of float
  | LitDecimal of string  (* Stored as normalized string *)
  | LitString of string
  | LitBool of bool
  | LitUnit
  | Var of string
  | Call of string * expr list  (* Function call *)
  | If of expr * expr list * expr list option  (* condition, then, else *)
  | While of expr * expr list  (* condition, body *)
  | Loop of expr list  (* Infinite loop *)
  | And of expr * expr  (* short-circuit and *)
  | Or of expr * expr   (* short-circuit or *)
  | Break
  | Continue
  | ForEach of string * type_kind * expr * expr list  (* var, type, collection, body *)
  | Set of string * type_kind * expr  (* var, type, value *)
  | Return of expr
  (* Core IR constructs *)
  | Label of string
  | Goto of string
  | IfNot of expr * string  (* condition, label *)
  | Try of expr list * string * type_kind * expr list  (* try_body, catch_var, catch_type, catch_body *)
  | Cond of (expr * expr list) list  (* list of (condition, body) branches *)
  | LitArray of expr list  (* [1 2 3] *)
  | LitMap of (expr * expr) list  (* {"key" "value" "key2" "value2"} *)

(* Function parameter *)
type param = {
  param_name : string;
  param_type : type_kind;
}

(* Function definition *)
type func_def = {
  func_name : string;
  func_params : param list;
  func_return_type : type_kind;
  func_body : expr list;
}

(* Test case for test-spec framework *)
type test_case = {
  test_description : string;
  test_inputs : expr list;
  test_expected : expr;
}

type test_spec = {
  test_func_name : string;
  test_cases : test_case list;
}

(* Module definition *)
type module_def = {
  module_name : string;
  module_imports : string list;
  module_functions : func_def list;
  module_tests : test_spec list;
  module_note : string option;
}

(* Pretty printing *)
let rec string_of_expr = function
  | LitInt n -> Int64.to_string n
  | LitFloat f -> string_of_float f
  | LitDecimal s -> s
  | LitString s -> "\"" ^ String.escaped s ^ "\""
  | LitBool b -> if b then "true" else "false"
  | LitUnit -> "unit"
  | Var name -> name
  | Call (func, args) ->
      let args_str = String.concat " " (List.map string_of_expr args) in
      "(" ^ func ^ " " ^ args_str ^ ")"
  | If (cond, then_body, else_body) ->
      let then_str = String.concat " " (List.map string_of_expr then_body) in
      let else_str = match else_body with
        | Some body -> " " ^ String.concat " " (List.map string_of_expr body)
        | None -> ""
      in
      "(if " ^ string_of_expr cond ^ " " ^ then_str ^ else_str ^ ")"
  | While (cond, body) ->
      let body_str = String.concat " " (List.map string_of_expr body) in
      "(while " ^ string_of_expr cond ^ " " ^ body_str ^ ")"
  | Loop body ->
      let body_str = String.concat " " (List.map string_of_expr body) in
      "(loop " ^ body_str ^ ")"
  | And (a, b) -> "(and " ^ string_of_expr a ^ " " ^ string_of_expr b ^ ")"
  | Or (a, b) -> "(or " ^ string_of_expr a ^ " " ^ string_of_expr b ^ ")"
  | Break -> "(break)"
  | Continue -> "(continue)"
  | ForEach (var, ty, coll, body) ->
      let body_str = String.concat " " (List.map string_of_expr body) in
      "(for-each " ^ var ^ " " ^ string_of_type ty ^ " " ^ string_of_expr coll ^ " " ^ body_str ^ ")"
  | Set (var, ty, value) ->
      "(set " ^ var ^ " " ^ string_of_type ty ^ " " ^ string_of_expr value ^ ")"
  | Return expr -> "(ret " ^ string_of_expr expr ^ ")"
  | Label name -> "(label " ^ name ^ ")"
  | Goto name -> "(goto " ^ name ^ ")"
  | IfNot (cond, label) -> "(ifnot " ^ string_of_expr cond ^ " " ^ label ^ ")"
  | Try (try_body, catch_var, catch_type, catch_body) ->
      let try_str = String.concat " " (List.map string_of_expr try_body) in
      let catch_str = String.concat " " (List.map string_of_expr catch_body) in
       "(try " ^ try_str ^ " (catch " ^ catch_var ^ " " ^ string_of_type catch_type ^ " " ^ catch_str ^ "))"
  | Cond branches ->
      let branch_strs = List.map (fun (cond, body) ->
        let body_str = String.concat " " (List.map string_of_expr body) in
        "(" ^ string_of_expr cond ^ " " ^ body_str ^ ")"
      ) branches in
      "(cond " ^ String.concat " " branch_strs ^ ")"
  | LitArray elems ->
      "[" ^ String.concat " " (List.map string_of_expr elems) ^ "]"
  | LitMap pairs ->
      let pair_strs = List.map (fun (k, v) -> string_of_expr k ^ " " ^ string_of_expr v) pairs in
      "{" ^ String.concat " " pair_strs ^ "}"
