#include "type_checker.h"
#include <string.h>
#include <stdio.h>

void type_checker_init(TypeChecker* tc) {
    tc->has_error = false;
    strcpy(tc->error_code, "NONE");
    tc->error_msg[0] = '\0';
    tc->error_line = 0;
    tc->error_col = 0;
}

static void type_error(TypeChecker* tc, const char* code, const char* msg, int line) {
    tc->has_error = true;
    strncpy(tc->error_code, code, sizeof(tc->error_code) - 1);
    strncpy(tc->error_msg, msg, sizeof(tc->error_msg) - 1);
    tc->error_line = line;
    tc->error_col = 0;
}

// Get type name as string
const char* type_to_string(Type* type) {
    if (!type) return "unknown";
    
    switch (type->kind) {
        case TYPE_INT: return "int";
        case TYPE_FLOAT: return "float";
        case TYPE_STRING: return "string";
        case TYPE_BOOL: return "bool";
        case TYPE_UNIT: return "unit";
        case TYPE_I8: return "i8";
        case TYPE_I16: return "i16";
        case TYPE_I32: return "i32";
        case TYPE_I64: return "i64";
        case TYPE_U8: return "u8";
        case TYPE_U16: return "u16";
        case TYPE_U32: return "u32";
        case TYPE_U64: return "u64";
        case TYPE_F32: return "f32";
        case TYPE_F64: return "f64";
        case TYPE_ARRAY: return "array";
        case TYPE_MAP: return "map";
        case TYPE_JSON: return "json";
        default: return "unknown";
    }
}

// Check if two types are exactly equal
bool type_equal(Type* t1, Type* t2) {
    if (!t1 || !t2) return false;
    return t1->kind == t2->kind;
}

// Check if types are compatible (allows some coercion)
bool type_compatible(Type* t1, Type* t2) {
    if (!t1 || !t2) return false;
    
    // Exact match
    if (t1->kind == t2->kind) return true;
    
    // Legacy int/float compatibility
    if ((t1->kind == TYPE_INT || t1->kind == TYPE_I64) && 
        (t2->kind == TYPE_INT || t2->kind == TYPE_I64)) {
        return true;
    }
    
    if ((t1->kind == TYPE_FLOAT || t1->kind == TYPE_F64) && 
        (t2->kind == TYPE_FLOAT || t2->kind == TYPE_F64)) {
        return true;
    }
    
    return false;
}

// Type check an expression recursively
bool type_check_expr(TypeChecker* tc, Expr* expr) {
    if (!expr) return true;
    
    switch (expr->kind) {
        case EXPR_LIT_INT:
            // Integer literals should have explicit type
            if (!expr->type) {
                type_error(tc, "MISSING_TYPE", "Integer literal missing type annotation", 0);
                return false;
            }
            break;
            
        case EXPR_LIT_FLOAT:
            if (!expr->type) {
                type_error(tc, "MISSING_TYPE", "Float literal missing type annotation", 0);
                return false;
            }
            break;
            
        case EXPR_LIT_STRING:
            if (!expr->type || expr->type->kind != TYPE_STRING) {
                type_error(tc, "TYPE_MISMATCH", "String literal must have string type", 0);
                return false;
            }
            break;
            
        case EXPR_LIT_BOOL:
            if (!expr->type || expr->type->kind != TYPE_BOOL) {
                type_error(tc, "TYPE_MISMATCH", "Boolean literal must have bool type", 0);
                return false;
            }
            break;
            
        case EXPR_LIT_UNIT:
            if (!expr->type || expr->type->kind != TYPE_UNIT) {
                type_error(tc, "TYPE_MISMATCH", "Unit literal must have unit type", 0);
                return false;
            }
            break;
            
        case EXPR_APPLY:
            // Type check function application
            if (expr->data.apply.func) {
                if (!type_check_expr(tc, expr->data.apply.func)) return false;
            }
            
            // Type check all arguments
            ExprList* arg = expr->data.apply.args;
            while (arg) {
                if (!type_check_expr(tc, arg->expr)) return false;
                arg = arg->next;
            }
            break;
            
        case EXPR_IF:
            // Check condition is bool
            if (expr->data.if_expr.cond) {
                if (!type_check_expr(tc, expr->data.if_expr.cond)) return false;
                if (expr->data.if_expr.cond->type && 
                    expr->data.if_expr.cond->type->kind != TYPE_BOOL) {
                    type_error(tc, "TYPE_MISMATCH", 
                        "If condition must be bool type", 0);
                    return false;
                }
            }
            
            // Check then and else branches
            if (!type_check_expr(tc, expr->data.if_expr.then_expr)) return false;
            if (!type_check_expr(tc, expr->data.if_expr.else_expr)) return false;
            
            // Then and else must have compatible types
            if (expr->data.if_expr.then_expr && expr->data.if_expr.else_expr) {
                Type* then_type = expr->data.if_expr.then_expr->type;
                Type* else_type = expr->data.if_expr.else_expr->type;
                if (!type_compatible(then_type, else_type)) {
                    char msg[256];
                    snprintf(msg, sizeof(msg), 
                        "If branches have incompatible types: %s vs %s",
                        type_to_string(then_type), type_to_string(else_type));
                    type_error(tc, "TYPE_MISMATCH", msg, 0);
                    return false;
                }
            }
            break;
            
        case EXPR_SEQ:
            // Type check all expressions in sequence
            {
                ExprList* seq = expr->data.tuple.elements;
                while (seq) {
                    if (!type_check_expr(tc, seq->expr)) return false;
                    seq = seq->next;
                }
            }
            break;
            
        case EXPR_BINARY:
            // Type check binary operations
            if (!type_check_expr(tc, expr->data.binary.left)) return false;
            if (!type_check_expr(tc, expr->data.binary.right)) return false;
            
            // Check operand types are compatible
            Type* left = expr->data.binary.left->type;
            Type* right = expr->data.binary.right->type;
            
            if (!type_compatible(left, right)) {
                char msg[256];
                snprintf(msg, sizeof(msg), 
                    "Binary operation has incompatible operands: %s vs %s",
                    type_to_string(left), type_to_string(right));
                type_error(tc, "TYPE_MISMATCH", msg, 0);
                return false;
            }
            break;
            
        default:
            // For other expression types, just pass for now
            break;
    }
    
    return !tc->has_error;
}

// Type check a definition (function)
static bool type_check_definition(TypeChecker* tc, Definition* def) {
    if (!def) return true;
    
    // Only check functions for now
    if (def->kind != DEF_FUNCTION) return true;
    
    // Check function has return type
    if (!def->data.func.return_type) {
        char msg[256];
        snprintf(msg, sizeof(msg), 
            "Function '%s' missing return type", def->name);
        type_error(tc, "MISSING_RETURN_TYPE", msg, 0);
        return false;
    }
    
    // Check all parameters have types
    ParamList* param = def->data.func.params;
    while (param) {
        if (!param->param->type) {
            char msg[256];
            snprintf(msg, sizeof(msg), 
                "Parameter '%s' in function '%s' missing type",
                param->param->name, def->name);
            type_error(tc, "MISSING_PARAM_TYPE", msg, 0);
            return false;
        }
        param = param->next;
    }
    
    // Type check function body
    if (!type_check_expr(tc, def->data.func.body)) {
        return false;
    }
    
    return true;
}

// Type check entire module
TypeCheckResult type_check_module(Module* module) {
    TypeCheckResult result;
    result.is_valid = true;
    strcpy(result.error_code, "NONE");
    result.error_msg[0] = '\0';
    result.line = 0;
    result.col = 0;
    
    if (!module) {
        result.is_valid = false;
        strcpy(result.error_code, "INVALID_MODULE");
        strcpy(result.error_msg, "Module is NULL");
        return result;
    }
    
    TypeChecker tc;
    type_checker_init(&tc);
    
    // Type check all definitions
    DefList* def = module->definitions;
    while (def) {
        if (!type_check_definition(&tc, def->def)) {
            result.is_valid = false;
            strcpy(result.error_code, tc.error_code);
            strcpy(result.error_msg, tc.error_msg);
            result.line = tc.error_line;
            result.col = tc.error_col;
            return result;
        }
        def = def->next;
    }
    
    return result;
}
