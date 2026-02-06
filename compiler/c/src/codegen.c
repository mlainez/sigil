#include "codegen.h"
#include <string.h>
#include <stdarg.h>

void codegen_init(Codegen* gen, FILE* output) {
    gen->output = output;
    gen->indent_level = 0;
}

static void emit(Codegen* gen, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vfprintf(gen->output, fmt, args);
    va_end(args);
}

static void emit_indent(Codegen* gen) {
    for (int i = 0; i < gen->indent_level; i++) {
        fprintf(gen->output, "    ");
    }
}

void codegen_expr(Codegen* gen, Expr* expr) {
    switch (expr->kind) {
        case EXPR_LIT_INT:
            emit(gen, "value_int(%lld)", (long long)expr->data.int_val);
            break;

        case EXPR_LIT_STRING:
            emit(gen, "value_string(\"%s\")", expr->data.string_val);
            break;

        case EXPR_LIT_BOOL:
            emit(gen, "value_bool(%s)", expr->data.bool_val ? "true" : "false");
            break;

        case EXPR_LIT_UNIT:
            emit(gen, "value_unit()");
            break;

        case EXPR_VAR:
            emit(gen, "%s", expr->data.var.name);
            break;

        case EXPR_BINARY: {
            emit(gen, "value_int(");
            codegen_expr(gen, expr->data.binary.left);
            emit(gen, "->data.int_val ");

            switch (expr->data.binary.op) {
                case BIN_ADD: emit(gen, "+"); break;
                case BIN_SUB: emit(gen, "-"); break;
                case BIN_MUL: emit(gen, "*"); break;
                case BIN_DIV: emit(gen, "/"); break;
                case BIN_LT: emit(gen, "<"); break;
                case BIN_GT: emit(gen, ">"); break;
                case BIN_LTE: emit(gen, "<="); break;
                case BIN_GTE: emit(gen, ">="); break;
                case BIN_EQ: emit(gen, "=="); break;
                default: break;
            }

            emit(gen, " ");
            codegen_expr(gen, expr->data.binary.right);
            emit(gen, "->data.int_val)");
            break;
        }

        case EXPR_IF:
            emit(gen, "(");
            codegen_expr(gen, expr->data.if_expr.cond);
            emit(gen, "->data.bool_val ? ");
            codegen_expr(gen, expr->data.if_expr.then_expr);
            emit(gen, " : ");
            codegen_expr(gen, expr->data.if_expr.else_expr);
            emit(gen, ")");
            break;

        case EXPR_APPLY:
            emit(gen, "((Closure*)(");
            codegen_expr(gen, expr->data.apply.func);
            emit(gen, ")->data.closure)->func((Value*[]){");

            ExprList* args = expr->data.apply.args;
            while (args) {
                codegen_expr(gen, args->expr);
                if (args->next) emit(gen, ", ");
                args = args->next;
            }

            emit(gen, "}, %d)", 0); // arg count
            break;

        case EXPR_SEQ: {
            emit(gen, "({\n");
            gen->indent_level++;

            ExprList* exprs = expr->data.seq.exprs;
            while (exprs->next) {
                emit_indent(gen);
                codegen_expr(gen, exprs->expr);
                emit(gen, ";\n");
                exprs = exprs->next;
            }

            emit_indent(gen);
            codegen_expr(gen, exprs->expr);
            emit(gen, ";\n");

            gen->indent_level--;
            emit_indent(gen);
            emit(gen, "})");
            break;
        }

        default:
            emit(gen, "value_unit()");
            break;
    }
}

static void codegen_function(Codegen* gen, Definition* def) {
    emit(gen, "Value* %s(", def->name);

    ParamList* params = def->data.func.params;
    while (params) {
        emit(gen, "Value* %s", params->param->name);
        if (params->next) emit(gen, ", ");
        params = params->next;
    }

    emit(gen, ") {\n");
    gen->indent_level++;

    emit_indent(gen);
    emit(gen, "return ");
    codegen_expr(gen, def->data.func.body);
    emit(gen, ";\n");

    gen->indent_level--;
    emit(gen, "}\n\n");
}

void codegen_module(Codegen* gen, Module* mod) {
    // Emit includes
    emit(gen, "#include <stdio.h>\n");
    emit(gen, "#include <stdlib.h>\n");
    emit(gen, "#include \"runtime.h\"\n\n");

    // Emit forward declarations
    DefList* defs = mod->definitions;
    while (defs) {
        if (defs->def->kind == DEF_FUNCTION) {
            emit(gen, "Value* %s(", defs->def->name);
            ParamList* params = defs->def->data.func.params;
            while (params) {
                emit(gen, "Value* %s", params->param->name);
                if (params->next) emit(gen, ", ");
                params = params->next;
            }
            emit(gen, ");\n");
        }
        defs = defs->next;
    }
    emit(gen, "\n");

    // Emit definitions
    defs = mod->definitions;
    while (defs) {
        if (defs->def->kind == DEF_FUNCTION) {
            codegen_function(gen, defs->def);
        }
        defs = defs->next;
    }

    // Emit main function
    emit(gen, "int main(int argc, char** argv) {\n");
    emit(gen, "    runtime_init();\n");
    emit(gen, "    \n");
    emit(gen, "    // Call main function if exists\n");
    emit(gen, "    Value* result = main_func();\n");
    emit(gen, "    \n");
    emit(gen, "    runtime_cleanup();\n");
    emit(gen, "    return 0;\n");
    emit(gen, "}\n");
}
