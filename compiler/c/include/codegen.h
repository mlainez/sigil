#ifndef CODEGEN_H
#define CODEGEN_H

#include "ast.h"
#include "runtime.h"
#include <stdio.h>

typedef struct {
    FILE* output;
    int indent_level;
} Codegen;

void codegen_init(Codegen* gen, FILE* output);
void codegen_module(Codegen* gen, Module* mod);
void codegen_expr(Codegen* gen, Expr* expr);

#endif // CODEGEN_H
