(* AISL Type System *)

type type_kind =
  | TInt
  | TFloat
  | TDecimal
  | TString
  | TBool
  | TUnit
  | TArray of type_kind
  | TMap of type_kind * type_kind
  | TJson
  | TRegex
  | TProcess
  | TSocket
  | TFunction of type_kind list * type_kind

let rec string_of_type = function
  | TInt -> "int"
  | TFloat -> "float"
  | TDecimal -> "decimal"
  | TString -> "string"
  | TBool -> "bool"
  | TUnit -> "unit"
  | TArray t -> "array<" ^ string_of_type t ^ ">"
  | TMap (k, v) -> "map<" ^ string_of_type k ^ ", " ^ string_of_type v ^ ">"
  | TJson -> "json"
  | TRegex -> "regex"
  | TProcess -> "process"
  | TSocket -> "socket"
  | TFunction (params, ret) ->
      let params_str = String.concat ", " (List.map string_of_type params) in
      "(" ^ params_str ^ " -> " ^ string_of_type ret ^ ")"
