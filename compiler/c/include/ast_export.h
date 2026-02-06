#ifndef AST_EXPORT_H
#define AST_EXPORT_H

#include "ast.h"
#include <stdio.h>

// Export AST to S-expression format
void ast_export_module(FILE* out, Module* module);
void ast_export_definition(FILE* out, Definition* def);
void ast_export_expr(FILE* out, Expr* expr);
void ast_export_type(FILE* out, Type* type);

#endif // AST_EXPORT_H
