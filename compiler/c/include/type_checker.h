#ifndef TYPE_CHECKER_H
#define TYPE_CHECKER_H

#include "ast.h"
#include <stdbool.h>

// Type checking result
typedef struct {
    bool is_valid;
    char error_code[64];
    char error_msg[512];
    int line;
    int col;
} TypeCheckResult;

// Type checker context
typedef struct {
    bool has_error;
    char error_code[64];
    char error_msg[512];
    int error_line;
    int error_col;
} TypeChecker;

// Initialize type checker
void type_checker_init(TypeChecker* tc);

// Check if two types are compatible
bool type_compatible(Type* t1, Type* t2);

// Check if types are exactly equal
bool type_equal(Type* t1, Type* t2);

// Type check an expression
bool type_check_expr(TypeChecker* tc, Expr* expr);

// Type check a module
TypeCheckResult type_check_module(Module* module);

// Get type name as string (for error messages)
const char* type_to_string(Type* type);

#endif // TYPE_CHECKER_H
