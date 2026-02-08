#define _POSIX_C_SOURCE 200809L
#include "ast.h"
#include <stdlib.h>
#include <string.h>

// ============================================
// TYPE CONSTRUCTORS
// ============================================

Type* type_new(TypeKind kind) {
    Type* t = malloc(sizeof(Type));
    t->kind = kind;
    return t;
}

Type* type_int() {
    return type_new(TYPE_INT);
}

Type* type_string() {
    return type_new(TYPE_STRING);
}

Type* type_bool() {
    return type_new(TYPE_BOOL);
}

Type* type_unit() {
    return type_new(TYPE_UNIT);
}

Type* type_function(TypeList* params, Type* ret) {
    Type* t = type_new(TYPE_FUNCTION);
    t->data.func.param_types = params;
    t->data.func.return_type = ret;
    return t;
}

Type* type_channel(Type* element) {
    Type* t = type_new(TYPE_CHANNEL);
    t->data.generic.element_type = element;
    return t;
}

Type* type_future(Type* element) {
    Type* t = type_new(TYPE_FUTURE);
    t->data.generic.element_type = element;
    return t;
}

Type* type_float() {
    return type_new(TYPE_FLOAT);
}

// Internal aliases - i64/f64 map to int/float
// These exist for backward compatibility with parser/compiler
Type* type_i64() {
    return type_new(TYPE_INT);  // int is always i64
}

Type* type_f64() {
    return type_new(TYPE_FLOAT);  // float is always f64
}

Type* type_array(Type* element) {
    Type* t = type_new(TYPE_ARRAY);
    t->data.generic.element_type = element;
    return t;
}

Type* type_map(Type* key, Type* value) {
    (void)key; // unused for now
    Type* t = type_new(TYPE_MAP);
    t->data.generic.element_type = value;
    return t;
}

Type* type_json() {
    return type_new(TYPE_JSON);
}

// ============================================
// EXPRESSION CONSTRUCTORS
// ============================================

Expr* expr_new(ExprKind kind, Type* type) {
    Expr* e = malloc(sizeof(Expr));
    e->kind = kind;
    e->type = type;
    return e;
}

Expr* expr_lit_int(int64_t val) {
    Expr* e = expr_new(EXPR_LIT_INT, type_int());
    e->data.int_val = val;
    return e;
}

Expr* expr_lit_string(const char* val) {
    Expr* e = expr_new(EXPR_LIT_STRING, type_string());
    e->data.string_val = strdup(val);
    return e;
}

Expr* expr_lit_float(double val) {
    Expr* e = expr_new(EXPR_LIT_FLOAT, type_f64());
    e->data.float_val = val;
    return e;
}

Expr* expr_lit_bool(bool val) {
    Expr* e = expr_new(EXPR_LIT_BOOL, type_bool());
    e->data.bool_val = val;
    return e;
}

Expr* expr_lit_unit() {
    return expr_new(EXPR_LIT_UNIT, type_unit());
}

Expr* expr_var(const char* name, Type* type) {
    Expr* e = expr_new(EXPR_VAR, type);
    e->data.var.name = strdup(name);
    return e;
}

Expr* expr_binary(BinaryOp op, Expr* left, Expr* right, Type* type) {
    Expr* e = expr_new(EXPR_BINARY, type);
    e->data.binary.op = op;
    e->data.binary.left = left;
    e->data.binary.right = right;
    return e;
}

Expr* expr_apply(Expr* func, ExprList* args, Type* type) {
    Expr* e = expr_new(EXPR_APPLY, type);
    e->data.apply.func = func;
    e->data.apply.args = args;
    return e;
}

Expr* expr_if(Expr* cond, Expr* then_expr, Expr* else_expr, Type* type) {
    Expr* e = expr_new(EXPR_IF, type);
    e->data.if_expr.cond = cond;
    e->data.if_expr.then_expr = then_expr;
    e->data.if_expr.else_expr = else_expr;
    return e;
}

Expr* expr_seq(ExprList* exprs, Type* type) {
    Expr* e = expr_new(EXPR_SEQ, type);
    e->data.seq.exprs = exprs;
    return e;
}

Expr* expr_io_write(Expr* handle, Expr* data, Type* type) {
    Expr* e = expr_new(EXPR_IO_WRITE, type);
    e->data.io_write.handle = handle;
    e->data.io_write.data = data;
    return e;
}

Expr* expr_io_read(Expr* handle, Type* type) {
    Expr* e = expr_new(EXPR_IO_READ, type);
    e->data.io_read.handle = handle;
    return e;
}

Expr* expr_io_open(Expr* path, Expr* mode, Type* type) {
    Expr* e = expr_new(EXPR_IO_OPEN, type);
    e->data.io_open.path = path;
    e->data.io_open.mode = mode;
    return e;
}

Expr* expr_io_close(Expr* handle, Type* type) {
    Expr* e = expr_new(EXPR_IO_CLOSE, type);
    e->data.io_close.handle = handle;
    return e;
}

Expr* expr_let(BindingList* bindings, Expr* body, Type* type) {
    Expr* e = expr_new(EXPR_LET, type);
    e->data.let.bindings = bindings;
    e->data.let.body = body;
    return e;
}

Expr* expr_while(Expr* cond, Expr* body, Type* type) {
    Expr* e = expr_new(EXPR_WHILE, type);
    e->data.while_loop.cond = cond;
    e->data.while_loop.body = body;
    return e;
}

Expr* expr_return(Expr* value, Type* type) {
    Expr* e = expr_new(EXPR_RETURN, type);
    e->data.return_expr.value = value;
    return e;
}

// ============================================
// LIST CONSTRUCTORS
// ============================================

ExprList* expr_list_new(Expr* expr, ExprList* next) {
    ExprList* list = malloc(sizeof(ExprList));
    list->expr = expr;
    list->next = next;
    return list;
}

ParamList* param_list_new(const char* name, Type* type, ParamList* next) {
    ParamList* list = malloc(sizeof(ParamList));
    list->param = malloc(sizeof(Param));
    list->param->name = strdup(name);
    list->param->type = type;
    list->next = next;
    return list;
}

BindingList* binding_list_new(const char* name, Type* type, Expr* value, BindingList* next) {
    BindingList* list = malloc(sizeof(BindingList));
    list->binding = malloc(sizeof(Binding));
    list->binding->name = strdup(name);
    list->binding->type = type;
    list->binding->value = value;
    list->next = next;
    return list;
}

// ============================================
// CLEANUP FUNCTIONS
// ============================================

void free_type(Type* type) {
    if (!type) return;
    // Simplified - in production, recursively free
    free(type);
}

void free_expr(Expr* expr) {
    if (!expr) return;
    // Simplified - in production, recursively free all fields
    free(expr);
}

void free_module(Module* mod) {
    if (!mod) return;
    free(mod->name);
    // Free definitions...
    free(mod);
}
