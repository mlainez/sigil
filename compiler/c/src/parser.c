#define _POSIX_C_SOURCE 200809L
#include "parser.h"
#include "test_framework.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

void parser_init(Parser* parser, Lexer* lexer) {
    parser->lexer = lexer;
    parser->current = lexer_next(lexer);
    parser->peek_tok = lexer_next(lexer);
    parser->has_error = false;
    strcpy(parser->error_code, "NONE");
}

// Error reporting with categorized error codes
static void parser_error_code(Parser* parser, const char* code, const char* msg) {
    parser->has_error = true;
    strncpy(parser->error_code, code, sizeof(parser->error_code) - 1);
    snprintf(parser->error_msg, sizeof(parser->error_msg),
             "Parse error at line %d: %s", parser->current.line, msg);
}

static void parser_error(Parser* parser, const char* msg) {
    parser_error_code(parser, "PARSE_ERROR", msg);
}

static Token parser_advance(Parser* parser) {
    Token old = parser->current;
    parser->current = parser->peek_tok;
    parser->peek_tok = lexer_next(parser->lexer);
    return old;
}

static bool parser_expect(Parser* parser, TokenKind kind) {
    if (parser->current.kind != kind) {
        parser_error(parser, "Unexpected token");
        return false;
    }
    parser_advance(parser);
    return true;
}

Type* parser_parse_type(Parser* parser) {
    Token tok = parser->current;

    switch (tok.kind) {
        case TOK_TYPE_I8:
            parser_advance(parser);
            return type_i8();
        case TOK_TYPE_I16:
            parser_advance(parser);
            return type_i16();
        case TOK_TYPE_I32:
            parser_advance(parser);
            return type_i32();
        case TOK_TYPE_I64:
            parser_advance(parser);
            return type_i64();
        case TOK_TYPE_U8:
            parser_advance(parser);
            return type_u8();
        case TOK_TYPE_U16:
            parser_advance(parser);
            return type_u16();
        case TOK_TYPE_U32:
            parser_advance(parser);
            return type_u32();
        case TOK_TYPE_U64:
            parser_advance(parser);
            return type_u64();
        case TOK_TYPE_F32:
            parser_advance(parser);
            return type_f32();
        case TOK_TYPE_F64:
            parser_advance(parser);
            return type_f64();
        case TOK_TYPE_STRING:
            parser_advance(parser);
            return type_string();
        case TOK_TYPE_BOOL:
            parser_advance(parser);
            return type_bool();
        case TOK_TYPE_UNIT:
            parser_advance(parser);
            return type_unit();
        case TOK_TYPE_ARRAY:
            parser_advance(parser);
            return type_array(type_unit());
        case TOK_TYPE_MAP:
            parser_advance(parser);
            return type_map(type_unit(), type_unit());
        case TOK_TYPE_JSON:
            parser_advance(parser);
            return type_json();
        default:
            parser_error(parser, "Expected type");
            return type_unit();
    }
}

static ExprList* parser_parse_expr_list(Parser* parser) {
    if (parser->current.kind == TOK_RBRACKET) {
        return NULL;
    }

    Expr* expr = parser_parse_expr(parser);
    ExprList* rest = NULL;

    if (parser->current.kind == TOK_COMMA) {
        parser_advance(parser);
        rest = parser_parse_expr_list(parser);
    }

    return expr_list_new(expr, rest);
}

static BindingList* parser_parse_bindings(Parser* parser) {
    if (parser->current.kind == TOK_RBRACKET) {
        return NULL;
    }

    parser_expect(parser, TOK_LPAREN);
    char* name = strdup(parser->current.value.string_val);
    parser_advance(parser);
    parser_expect(parser, TOK_COLON);
    Type* type = parser_parse_type(parser);
    parser_expect(parser, TOK_EQUAL);
    Expr* value = parser_parse_expr(parser);
    parser_expect(parser, TOK_RPAREN);

    BindingList* rest = NULL;
    if (parser->current.kind == TOK_COMMA) {
        parser_advance(parser);
        rest = parser_parse_bindings(parser);
    }

    return binding_list_new(name, type, value, rest);
}

Expr* parser_parse_expr(Parser* parser) {
    if (!parser_expect(parser, TOK_LPAREN)) {
        return expr_lit_unit();
    }

    Token tok = parser->current;

    // Literals
    if (tok.kind == TOK_LIT_INT) {
        parser_advance(parser);
        int64_t val = parser->current.value.int_val;
        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_lit_int(val);
    }

    if (tok.kind == TOK_LIT_STRING) {
        parser_advance(parser);
        char* val = strdup(parser->current.value.string_val);
        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_lit_string(val);
    }

    if (tok.kind == TOK_LIT_BOOL) {
        parser_advance(parser);
        bool val = parser->current.kind == TOK_TRUE;
        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_lit_bool(val);
    }

    // Handle standalone true/false keywords
    if (tok.kind == TOK_TRUE) {
        parser_advance(parser);
        return expr_lit_bool(true);
    }

    if (tok.kind == TOK_FALSE) {
        parser_advance(parser);
        return expr_lit_bool(false);
    }

    if (tok.kind == TOK_LIT_UNIT) {
        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_lit_unit();
    }

    // Variable reference
    if (tok.kind == TOK_VAR) {
        parser_advance(parser);
        char* name = strdup(parser->current.value.string_val);
        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_var(name, type);
    }

    // Binary operations
    if (tok.kind == TOK_ADD || tok.kind == TOK_SUB ||
        tok.kind == TOK_MUL || tok.kind == TOK_DIV ||
        tok.kind == TOK_LT || tok.kind == TOK_GT ||
        tok.kind == TOK_LTE || tok.kind == TOK_GTE ||
        tok.kind == TOK_EQ) {

        BinaryOp op;
        if (tok.kind == TOK_ADD) op = BIN_ADD;
        else if (tok.kind == TOK_SUB) op = BIN_SUB;
        else if (tok.kind == TOK_MUL) op = BIN_MUL;
        else if (tok.kind == TOK_DIV) op = BIN_DIV;
        else if (tok.kind == TOK_LT) op = BIN_LT;
        else if (tok.kind == TOK_GT) op = BIN_GT;
        else if (tok.kind == TOK_LTE) op = BIN_LTE;
        else if (tok.kind == TOK_GTE) op = BIN_GTE;
        else op = BIN_EQ;

        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        Expr* left = parser_parse_expr(parser);
        Expr* right = parser_parse_expr(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_binary(op, left, right, type);
    }

    // If expression
    if (tok.kind == TOK_IF) {
        parser_advance(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        Expr* cond = parser_parse_expr(parser);
        parser_expect(parser, TOK_THEN);
        Expr* then_expr = parser_parse_expr(parser);
        parser_expect(parser, TOK_ELSE);
        Expr* else_expr = parser_parse_expr(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_if(cond, then_expr, else_expr, type);
    }

    // Sequence
    if (tok.kind == TOK_SEQ) {
        parser_advance(parser);
        parser_expect(parser, TOK_LBRACKET);
        ExprList* exprs = parser_parse_expr_list(parser);
        parser_expect(parser, TOK_RBRACKET);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_seq(exprs, type);
    }

    // Let - simplified to allow either brackets or no brackets
    if (tok.kind == TOK_LET) {
        parser_advance(parser);
        BindingList* bindings = NULL;

        // Try bracket syntax first
        if (parser->current.kind == TOK_LBRACKET) {
            parser_advance(parser);
            bindings = parser_parse_bindings(parser);
            if (!parser_expect(parser, TOK_RBRACKET)) {
                return expr_lit_unit();
            }
        }

        if (!parser_expect(parser, TOK_IN)) {
            return expr_lit_unit();
        }

        Expr* body = parser_parse_expr(parser);

        if (!parser_expect(parser, TOK_COLON)) {
            return expr_lit_unit();
        }

        Type* type = parser_parse_type(parser);

        if (!parser_expect(parser, TOK_RPAREN)) {
            return expr_lit_unit();
        }

        return expr_let(bindings, body, type);
    }

    // Apply
    if (tok.kind == TOK_APPLY) {
        parser_advance(parser);
        Expr* func = parser_parse_expr(parser);
        parser_expect(parser, TOK_LBRACKET);
        ExprList* args = parser_parse_expr_list(parser);
        parser_expect(parser, TOK_RBRACKET);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_apply(func, args, type);
    }

    // While
    if (tok.kind == TOK_WHILE) {
        parser_advance(parser);
        Expr* cond = parser_parse_expr(parser);
        parser_expect(parser, TOK_DO);
        Expr* body = parser_parse_expr(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_while(cond, body, type);
    }

    // IOWrite
    if (tok.kind == TOK_IO_WRITE) {
        parser_advance(parser);
        Expr* handle = parser_parse_expr(parser);
        Expr* data = parser_parse_expr(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_io_write(handle, data, type);
    }

    // IORead
    if (tok.kind == TOK_IO_READ) {
        parser_advance(parser);
        Expr* handle = parser_parse_expr(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_io_read(handle, type);
    }

    // IOOpen
    if (tok.kind == TOK_IO_OPEN) {
        parser_advance(parser);
        Expr* path = parser_parse_expr(parser);
        Expr* mode = parser_parse_expr(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_io_open(path, mode, type);
    }

    // IOClose
    if (tok.kind == TOK_IO_CLOSE) {
        parser_advance(parser);
        Expr* handle = parser_parse_expr(parser);
        parser_expect(parser, TOK_COLON);
        Type* type = parser_parse_type(parser);
        parser_expect(parser, TOK_RPAREN);
        return expr_io_close(handle, type);
    }

    parser_error(parser, "Unknown expression");
    parser_expect(parser, TOK_RPAREN);
    return expr_lit_unit();
}

// Forward declare v3 parser
static Definition* parser_parse_function_v3(Parser* parser);

// Parse v3.0 value expressions: literals, variables
static Expr* parser_parse_value_expr_v3(Parser* parser) {
    Token tok = parser->current;

    // Check for typed literal or nested call: (int type_name value) or (call func args...)
    if (tok.kind == TOK_LPAREN) {
        parser_advance(parser); // consume (
        Token inner = parser->current;
        
        if (inner.kind == TOK_LIT_INT) {
            // Typed integer literal: (int i32 42)
            parser_advance(parser); // consume 'int'
            Type* lit_type = parser_parse_type(parser); // parse type
            int64_t val = parser->current.value.int_val;
            parser_advance(parser); // consume value
            parser_expect(parser, TOK_RPAREN);
            return expr_lit_int(val);
        }
        
        if (inner.kind == TOK_LIT_STRING) {
            // Typed string literal: (string "hello")
            parser_advance(parser); // consume 'string'
            char* val = strdup(parser->current.value.string_val);
            parser_advance(parser); // consume value
            parser_expect(parser, TOK_RPAREN);
            return expr_lit_string(val);
        }
        
        if (inner.kind == TOK_CALL) {
            // Nested call expression: (call func arg1 arg2 ...)
            parser_advance(parser); // consume 'call'
            
            char* func_name = strdup(parser->current.value.string_val);
            parser_advance(parser);
            
            ExprList* args = NULL;
            ExprList* args_tail = NULL;
            while (parser->current.kind != TOK_RPAREN) {
                Expr* arg = parser_parse_value_expr_v3(parser);
                ExprList* new_arg = malloc(sizeof(ExprList));
                new_arg->expr = arg;
                new_arg->next = NULL;
                if (!args) {
                    args = new_arg;
                    args_tail = new_arg;
                } else {
                    args_tail->next = new_arg;
                    args_tail = new_arg;
                }
            }
            parser_expect(parser, TOK_RPAREN);
            
            Expr* func_expr = expr_var(func_name, type_unit());
            return expr_apply(func_expr, args, type_unit());
        }
        
        // Not a typed literal or call, consume and return unit
        while (parser->current.kind != TOK_RPAREN && parser->current.kind != TOK_EOF) {
            parser_advance(parser);
        }
        if (parser->current.kind == TOK_RPAREN) {
            parser_advance(parser);
        }
        return expr_lit_unit();
    }

    // Integer literal
    if (tok.kind == TOK_LIT_INT || tok.kind == TOK_INT) {
        int val = tok.value.int_val;
        parser_advance(parser);
        return expr_lit_int(val);
    }

    // Float literal
    if (tok.kind == TOK_FLOAT) {
        double val = tok.value.float_val;
        parser_advance(parser);
        return expr_lit_float(val);
    }

    // String literal (TOK_STRING is what the lexer produces for "...")
    if (tok.kind == TOK_STRING) {
        char* val = strdup(tok.value.string_val);
        parser_advance(parser);
        return expr_lit_string(val);
    }

    // Boolean literals
    if (tok.kind == TOK_TRUE) {
        parser_advance(parser);
        return expr_lit_bool(true);
    }

    if (tok.kind == TOK_FALSE) {
        parser_advance(parser);
        return expr_lit_bool(false);
    }

    // Variable reference (identifiers are variables)
    if (tok.kind == TOK_VAR || tok.kind == TOK_IDENTIFIER) {
        char* name = strdup(tok.value.string_val);
        parser_advance(parser);
        return expr_var(name, type_unit());
    }

    // For now, just consume and return unit
    parser_advance(parser);
    return expr_lit_unit();
}

// Parse v3.0 statements: call, set, if, goto, label, ret
static Expr* parser_parse_statements_v3(Parser* parser) {
    ExprList* stmts = NULL;

    while (parser->current.kind == TOK_LPAREN && parser->peek_tok.kind != TOK_RPAREN) {
        Token next = parser->peek_tok;

        if (next.kind == TOK_CALL) {
            // (call func arg arg ...)
            parser_advance(parser); // (
            parser_advance(parser); // call

            char* func_name = strdup(parser->current.value.string_val);
            parser_advance(parser);

            ExprList* args = NULL;
            while (parser->current.kind != TOK_RPAREN) {
                Expr* arg = parser_parse_value_expr_v3(parser);
                ExprList* new_arg = malloc(sizeof(ExprList));
                new_arg->expr = arg;
                new_arg->next = NULL;
                if (args) {
                    ExprList* cur = args;
                    while (cur->next) cur = cur->next;
                    cur->next = new_arg;
                } else {
                    args = new_arg;
                }
            }
            parser_expect(parser, TOK_RPAREN);

            Expr* func_expr = expr_var(func_name, type_unit());
            Expr* call_expr = expr_apply(func_expr, args, type_unit());

            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = call_expr;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }

        } else if (next.kind == TOK_SET) {
            // (set var type value) - type is MANDATORY
            parser_advance(parser); // (
            parser_advance(parser); // set

            char* var_name = strdup(parser->current.value.string_val);
            parser_advance(parser);

            // STRICT MODE: Type is REQUIRED for all variable declarations
            Type* var_type = NULL;
            // Check if current token is a type keyword (string, bool, unit, i8-u64, f32, f64, array, map, json)
            if ((parser->current.kind >= TOK_TYPE_STRING && parser->current.kind <= TOK_TYPE_JSON)) {
                var_type = parser_parse_type(parser);
            } else {
                // ERROR: Type is missing
                char error_msg[256];
                snprintf(error_msg, sizeof(error_msg), 
                    "Variable '%s' requires explicit type annotation. Use: (set %s <type> <value>)", 
                    var_name, var_name);
                parser_error_code(parser, "MISSING_TYPE", error_msg);
                return expr_seq(NULL, type_unit()); // Return empty to avoid crash
            }

            Expr* value = parser_parse_value_expr_v3(parser);
            parser_expect(parser, TOK_RPAREN);

            // Attach the explicit type annotation to the value expression
            // This ensures the compiler can track variable types
            // Always use the explicit annotation (e.g., i32) instead of generic types (e.g., TYPE_INT)
            value->type = var_type;

            // For now, just represent as an apply to a setter
            ExprList* args = malloc(sizeof(ExprList));
            args->expr = value;
            args->next = NULL;

            char set_func[256];
            snprintf(set_func, sizeof(set_func), "set_%s", var_name);
            Expr* func_expr = expr_var(set_func, type_unit());
            Expr* set_expr = expr_apply(func_expr, args, var_type);

            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = set_expr;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }

        } else if (next.kind == TOK_RET) {
            // (ret) or (ret value)
            parser_advance(parser); // (
            parser_advance(parser); // ret

            Expr* ret_val = expr_lit_unit();
            if (parser->current.kind != TOK_RPAREN) {
                ret_val = parser_parse_value_expr_v3(parser);
            }
            parser_expect(parser, TOK_RPAREN);

            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = ret_val;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }
            break; // ret is terminal

        } else if (next.kind == TOK_WHILE) {
            // (while condition body-statements)
            parser_advance(parser); // (
            parser_advance(parser); // while
            
            // Parse condition
            Expr* cond = parser_parse_value_expr_v3(parser);
            
            // Parse body statements recursively
            Expr* body = parser_parse_statements_v3(parser);
            
            parser_expect(parser, TOK_RPAREN);
            
            // Create EXPR_WHILE node
            Expr* while_expr = expr_while(cond, body, type_unit());
            
            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = while_expr;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }

        } else if (next.kind == TOK_LOOP) {
            // (loop body-statements) -> syntactic sugar for (while true body-statements)
            parser_advance(parser); // (
            parser_advance(parser); // loop
            
            // Parse body statements recursively
            Expr* body = parser_parse_statements_v3(parser);
            
            parser_expect(parser, TOK_RPAREN);
            
            // Create EXPR_WHILE node with true condition
            Expr* true_cond = expr_lit_bool(true);
            Expr* loop_expr = expr_while(true_cond, body, type_unit());
            
            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = loop_expr;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }

        } else if (next.kind == TOK_BREAK) {
            // (break)
            parser_advance(parser); // (
            parser_advance(parser); // break
            parser_expect(parser, TOK_RPAREN);
            
            // Create EXPR_BREAK node
            Expr* break_expr = malloc(sizeof(Expr));
            break_expr->kind = EXPR_BREAK;
            break_expr->type = type_unit();
            
            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = break_expr;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }

        } else if (next.kind == TOK_CONTINUE) {
            // (continue)
            parser_advance(parser); // (
            parser_advance(parser); // continue
            parser_expect(parser, TOK_RPAREN);
            
            // Create EXPR_CONTINUE node
            Expr* continue_expr = malloc(sizeof(Expr));
            continue_expr->kind = EXPR_CONTINUE;
            continue_expr->type = type_unit();
            
            ExprList* stmt = malloc(sizeof(ExprList));
            stmt->expr = continue_expr;
            stmt->next = NULL;
            if (stmts) {
                ExprList* cur = stmts;
                while (cur->next) cur = cur->next;
                cur->next = stmt;
            } else {
                stmts = stmt;
            }

        } else {
            // Unknown statement, skip to closing paren
            int depth = 1;
            parser_advance(parser);
            while (depth > 0 && parser->current.kind != TOK_EOF) {
                if (parser->current.kind == TOK_LPAREN) depth++;
                else if (parser->current.kind == TOK_RPAREN) depth--;
                if (depth > 0) parser_advance(parser);
            }
            if (depth > 0) break;
            parser_advance(parser);
        }
    }

    if (!stmts) {
        stmts = malloc(sizeof(ExprList));
        stmts->expr = expr_lit_unit();
        stmts->next = NULL;
    }

    return expr_seq(stmts, type_unit());
}

// V3 syntax parser for (fn name (params) (statements))
static Definition* parser_parse_function_v3(Parser* parser) {
    parser_expect(parser, TOK_LPAREN);
    parser_expect(parser, TOK_FN);

    char* name = strdup(parser->current.value.string_val);
    parser_advance(parser);

    // Parse parameters - Accept both syntaxes:
    // OLD: ((param_name type) (param_name type)) - double nested
    // NEW: param_name type param_name type       - flat [RECOMMENDED for LLMs]
    ParamList* params = NULL;
    ParamList* params_tail = NULL;
    
    // Check if using old syntax with parameter list paren
    bool has_param_list_paren = false;
    if (parser->current.kind == TOK_LPAREN) {
        // Lookahead: is the next token also a paren? Then it's old syntax
        // Otherwise treat first LPAREN as start of old-style param list
        has_param_list_paren = true;
        parser_advance(parser); // consume the opening (
    }
    
    // Parse parameters until we hit -> or )
    while (parser->current.kind != TOK_ARROW && parser->current.kind != TOK_RPAREN) {
        char* param_name = NULL;
        Type* param_type = NULL;
        
        if (parser->current.kind == TOK_LPAREN) {
            // OLD syntax: each param wrapped in parens
            parser_advance(parser); // consume (
            // Accept identifiers, var, and test keywords like "input", "expect", "delim" etc.
            if (parser->current.kind != TOK_IDENTIFIER && 
                parser->current.kind != TOK_VAR &&
                parser->current.kind != TOK_INPUT &&
                parser->current.kind != TOK_EXPECT) {
                parser_error(parser, "Expected parameter name in old syntax");
            }
            param_name = strdup(parser->current.value.string_val);
            parser_advance(parser);
            param_type = parser_parse_type(parser);
            parser_expect(parser, TOK_RPAREN); // consume )
        } else if (parser->current.kind == TOK_IDENTIFIER || 
                   parser->current.kind == TOK_VAR ||
                   parser->current.kind == TOK_INPUT ||
                   parser->current.kind == TOK_EXPECT) {
            // NEW flat syntax: no parens around params
            param_name = strdup(parser->current.value.string_val);
            parser_advance(parser);
            param_type = parser_parse_type(parser);
        } else {
            parser_error(parser, "Expected parameter definition");
        }
        
        ParamList* new_param = param_list_new(param_name, param_type, NULL);
        if (!params) {
            params = new_param;
            params_tail = new_param;
        } else {
            params_tail->next = new_param;
            params_tail = new_param;
        }
    }
    
    // If we consumed opening paren, expect closing paren
    if (has_param_list_paren) {
        parser_expect(parser, TOK_RPAREN);
    }

    // STRICT MODE: Return type is REQUIRED
    Type* return_type = NULL;
    if (parser->current.kind == TOK_ARROW) {
        parser_advance(parser);
        return_type = parser_parse_type(parser);
    } else {
        // ERROR: Return type is missing
        char error_msg[256];
        snprintf(error_msg, sizeof(error_msg), 
            "Function '%s' requires explicit return type. Use: (fn %s (...) -> <type> ...)", 
            name, name);
        parser_error_code(parser, "MISSING_RETURN_TYPE", error_msg);
        return_type = type_unit(); // Default to unit to avoid crash
    }

    // Skip effect annotations for now (pure, io, etc.)
    while (parser->current.kind == TOK_VAR) {
        // Check if it's an effect keyword
        char* tok_str = parser->current.value.string_val;
        if (strcmp(tok_str, "pure") == 0 || 
            strcmp(tok_str, "io") == 0 ||
            strcmp(tok_str, "net") == 0 ||
            strcmp(tok_str, "fs") == 0 ||
            strcmp(tok_str, "time") == 0 ||
            strcmp(tok_str, "random") == 0 ||
            strcmp(tok_str, "panic") == 0 ||
            strcmp(tok_str, "unsafe") == 0) {
            parser_advance(parser);
        } else {
            break;
        }
    }

    // Parse body statements
    Expr* body = parser_parse_statements_v3(parser);

    parser_expect(parser, TOK_RPAREN);

    Definition* def = malloc(sizeof(Definition));
    def->kind = DEF_FUNCTION;
    def->name = name;
    def->data.func.params = params;
    def->data.func.return_type = return_type;
    def->data.func.body = body;

    return def;
}

// Parse test case: (case "description" (input arg1 arg2) (expect result))
static TestCase* parser_parse_test_case(Parser* parser) {
    parser_expect(parser, TOK_LPAREN);
    parser_expect(parser, TOK_CASE);
    
    int line = parser->current.line;
    
    // Parse description string
    if (parser->current.kind != TOK_STRING) {
        parser_error(parser, "Expected test case description string");
        return NULL;
    }
    char* description = strdup(parser->current.value.string_val);
    parser_advance(parser);
    
    // Parse optional setup: (setup (set ...))
    MockSpecList* mocks = NULL;
    if (parser->current.kind == TOK_LPAREN && parser->peek_tok.kind == TOK_SETUP) {
        parser_advance(parser); // consume (
        parser_advance(parser); // consume setup
        // Parse setup expressions (for now, just skip)
        while (parser->current.kind != TOK_RPAREN && parser->current.kind != TOK_EOF) {
            if (parser->current.kind == TOK_LPAREN) {
                int depth = 1;
                parser_advance(parser);
                while (depth > 0 && parser->current.kind != TOK_EOF) {
                    if (parser->current.kind == TOK_LPAREN) depth++;
                    else if (parser->current.kind == TOK_RPAREN) depth--;
                    if (depth > 0) parser_advance(parser);
                }
                if (depth > 0) break;
            }
            parser_advance(parser);
        }
        parser_expect(parser, TOK_RPAREN);
    }
    
    // Parse optional mock: (mock (func args) result)
    if (parser->current.kind == TOK_LPAREN && parser->peek_tok.kind == TOK_MOCK) {
        parser_advance(parser); // consume (
        parser_advance(parser); // consume mock
        
        // Parse mock call: (func arg1 arg2 ...)
        parser_expect(parser, TOK_LPAREN);
        char* mock_func_name = strdup(parser->current.value.string_val);
        parser_advance(parser);
        
        ExprList* mock_args = NULL;
        ExprList* mock_args_tail = NULL;
        while (parser->current.kind != TOK_RPAREN) {
            Expr* arg = parser_parse_value_expr_v3(parser);
            ExprList* new_arg = malloc(sizeof(ExprList));
            new_arg->expr = arg;
            new_arg->next = NULL;
            if (!mock_args) {
                mock_args = new_arg;
                mock_args_tail = new_arg;
            } else {
                mock_args_tail->next = new_arg;
                mock_args_tail = new_arg;
            }
        }
        parser_expect(parser, TOK_RPAREN);
        
        // Parse mock return value
        Expr* mock_return = parser_parse_value_expr_v3(parser);
        
        MockSpec* mock = mock_spec_new(mock_func_name, mock_args, mock_return);
        mocks = mock_spec_list_new(mock, NULL);
        
        parser_expect(parser, TOK_RPAREN);
    }
    
    // Parse (input arg1 arg2 ...)
    parser_expect(parser, TOK_LPAREN);
    if (parser->current.kind != TOK_INPUT) {
        parser_error(parser, "Expected 'input' keyword in test case");
        return NULL;
    }
    parser_advance(parser); // consume INPUT
    
    ExprList* inputs = NULL;
    ExprList* inputs_tail = NULL;
    int input_count = 0;
    while (parser->current.kind != TOK_RPAREN && parser->current.kind != TOK_EOF) {
        if (input_count++ > 100) {
            parser_error(parser, "Too many inputs in test case (possible infinite loop)");
            return NULL;
        }
        Expr* arg = parser_parse_value_expr_v3(parser);
        ExprList* new_arg = malloc(sizeof(ExprList));
        new_arg->expr = arg;
        new_arg->next = NULL;
        if (!inputs) {
            inputs = new_arg;
            inputs_tail = new_arg;
        } else {
            inputs_tail->next = new_arg;
            inputs_tail = new_arg;
        }
    }
    parser_expect(parser, TOK_RPAREN);
    
    // Parse (expect result)
    parser_expect(parser, TOK_LPAREN);
    parser_expect(parser, TOK_EXPECT);
    Expr* expected = parser_parse_value_expr_v3(parser);
    parser_expect(parser, TOK_RPAREN);
    
    parser_expect(parser, TOK_RPAREN); // close case
    
    TestCase* tc = test_case_new(description, inputs, expected, line);
    tc->mocks = mocks;
    return tc;
}

// Parse test-spec: (test-spec function-name (case ...) ...)
static Definition* parser_parse_test_spec(Parser* parser) {
    parser_expect(parser, TOK_LPAREN);
    parser_expect(parser, TOK_TEST_SPEC);
    
    int line = parser->current.line;
    
    // Parse target function name
    char* target_func = strdup(parser->current.value.string_val);
    parser_advance(parser);
    
    // Parse test cases
    TestCaseList* test_cases = NULL;
    TestCaseList* test_cases_tail = NULL;
    
    while (parser->current.kind == TOK_LPAREN && parser->peek_tok.kind == TOK_CASE) {
        TestCase* tc = parser_parse_test_case(parser);
        if (!tc) break;
        
        TestCaseList* new_tc = test_case_list_new(tc, NULL);
        if (!test_cases) {
            test_cases = new_tc;
            test_cases_tail = new_tc;
        } else {
            test_cases_tail->next = new_tc;
            test_cases_tail = new_tc;
        }
    }
    
    parser_expect(parser, TOK_RPAREN);
    
    TestSpec* spec = test_spec_new(TEST_CASE, target_func, line);
    spec->data.test_cases = test_cases;
    
    Definition* def = malloc(sizeof(Definition));
    def->kind = DEF_TEST_SPEC;
    def->name = target_func;
    def->line = line;
    def->data.test.test_spec = spec;
    
    return def;
}

// Parse property-spec: (property-spec function-name (property ...) ...)
static Definition* parser_parse_property_spec(Parser* parser) {
    parser_expect(parser, TOK_LPAREN);
    parser_expect(parser, TOK_PROPERTY_SPEC);
    
    int line = parser->current.line;
    
    // Parse target function name
    char* target_func = strdup(parser->current.value.string_val);
    parser_advance(parser);
    
    // For now, just skip property definitions and create empty spec
    // TODO: Implement full property parsing
    while (parser->current.kind == TOK_LPAREN && parser->peek_tok.kind == TOK_PROPERTY) {
        int depth = 1;
        parser_advance(parser);
        while (depth > 0 && parser->current.kind != TOK_EOF) {
            if (parser->current.kind == TOK_LPAREN) depth++;
            else if (parser->current.kind == TOK_RPAREN) depth--;
            if (depth > 0) parser_advance(parser);
        }
        if (depth > 0) break;
        parser_advance(parser);
    }
    
    parser_expect(parser, TOK_RPAREN);
    
    TestSpec* spec = test_spec_new(TEST_PROPERTY, target_func, line);
    spec->data.properties = NULL; // TODO: populate with parsed properties
    
    Definition* def = malloc(sizeof(Definition));
    def->kind = DEF_PROPERTY_SPEC;
    def->name = target_func;
    def->line = line;
    def->data.property.property_spec = spec;
    
    return def;
}

// Parse meta-note: (meta-note "text")
static Definition* parser_parse_meta_note(Parser* parser) {
    parser_expect(parser, TOK_LPAREN);
    parser_expect(parser, TOK_META_NOTE);
    
    int line = parser->current.line;
    
    // Parse note text string
    if (parser->current.kind != TOK_STRING) {
        parser_error(parser, "Expected meta-note text string");
        return NULL;
    }
    char* note_text = strdup(parser->current.value.string_val);
    parser_advance(parser);
    
    parser_expect(parser, TOK_RPAREN);
    
    Definition* def = malloc(sizeof(Definition));
    def->kind = DEF_META_NOTE;
    def->name = NULL;
    def->line = line;
    def->data.meta_note.note_text = note_text;
    
    return def;
}

Module* parser_parse_module(Parser* parser) {
    parser_expect(parser, TOK_LPAREN);

    char* name = NULL;
    DefList* defs = NULL;

    // Check which syntax version
    if (parser->current.kind == TOK_MODULE) {
        // Old v0.2 syntax: (Module name [] [] [...defs...])
        parser_advance(parser);

        name = strdup(parser->current.value.string_val);
        parser_advance(parser);

        // Skip empty list []
        parser_expect(parser, TOK_LBRACKET);
        parser_expect(parser, TOK_RBRACKET);

        // Skip empty list [] (exports)
        parser_expect(parser, TOK_LBRACKET);
        parser_expect(parser, TOK_RBRACKET);

        // Parse definitions list
        parser_expect(parser, TOK_LBRACKET);
        while (parser->current.kind == TOK_LPAREN && parser->peek_tok.kind == TOK_DEF_FN) {
            parser_expect(parser, TOK_LPAREN);
            parser_expect(parser, TOK_DEF_FN);

            char* fname = strdup(parser->current.value.string_val);
            parser_advance(parser);

            parser_expect(parser, TOK_LBRACKET);
            ParamList* params = NULL;
            while (parser->current.kind != TOK_RBRACKET) {
                char* pname = strdup(parser->current.value.string_val);
                parser_advance(parser);
                parser_expect(parser, TOK_COLON);
                Type* ptype = parser_parse_type(parser);
                params = param_list_new(pname, ptype, params);
                if (parser->current.kind == TOK_COMMA) {
                    parser_advance(parser);
                }
            }
            parser_expect(parser, TOK_RBRACKET);

            // Skip empty locals list
            parser_expect(parser, TOK_LBRACKET);
            parser_expect(parser, TOK_RBRACKET);

            // Parse return type
            parser_expect(parser, TOK_ARROW);
            Type* ret_type = parser_parse_type(parser);

            // Parse body expression
            Expr* body = parser_parse_expr(parser);

            parser_expect(parser, TOK_RPAREN);

            Definition* def = malloc(sizeof(Definition));
            def->kind = DEF_FUNCTION;
            def->name = fname;
            def->data.func.params = params;
            def->data.func.return_type = ret_type;
            def->data.func.body = body;

            DefList* new_list = malloc(sizeof(DefList));
            new_list->def = def;
            new_list->next = defs;
            defs = new_list;
        }
        parser_expect(parser, TOK_RBRACKET);

        parser_expect(parser, TOK_RPAREN);

    } else if (parser->current.kind == TOK_MOD) {
        // New v3.0 syntax: (mod name (fn ...)* (test-spec ...)* (property-spec ...)* (meta-note ...)*)
        parser_advance(parser);

        name = strdup(parser->current.value.string_val);
        parser_advance(parser);

        while (parser->current.kind == TOK_LPAREN) {
            Definition* def = NULL;
            
            if (parser->peek_tok.kind == TOK_FN) {
                def = parser_parse_function_v3(parser);
            } else if (parser->peek_tok.kind == TOK_TEST_SPEC) {
                def = parser_parse_test_spec(parser);
            } else if (parser->peek_tok.kind == TOK_PROPERTY_SPEC) {
                def = parser_parse_property_spec(parser);
            } else if (parser->peek_tok.kind == TOK_META_NOTE) {
                def = parser_parse_meta_note(parser);
            } else {
                // Unknown definition, skip it
                int depth = 1;
                parser_advance(parser);
                while (depth > 0 && parser->current.kind != TOK_EOF) {
                    if (parser->current.kind == TOK_LPAREN) depth++;
                    else if (parser->current.kind == TOK_RPAREN) depth--;
                    if (depth > 0) parser_advance(parser);
                }
                if (depth > 0) break;
                parser_advance(parser);
                continue;
            }
            
            if (!def) break;
            DefList* new_list = malloc(sizeof(DefList));
            new_list->def = def;
            new_list->next = defs;
            defs = new_list;
        }

        parser_expect(parser, TOK_RPAREN);

    } else {
        parser_error(parser, "Expected 'Module' or 'mod'");
    }

    Module* mod = malloc(sizeof(Module));
    mod->name = name;
    mod->definitions = defs;

    return mod;
}
