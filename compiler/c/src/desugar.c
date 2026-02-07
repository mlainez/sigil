#include "desugar.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ============================================
// LABEL GENERATION
// ============================================

static int label_counter = 0;

static char* gen_label(const char* prefix) {
    char* label = malloc(64);
    snprintf(label, 64, "%s_%d", prefix, label_counter++);
    return label;
}

// ============================================
// LOOP CONTEXT
// ============================================

// Track loop start/end labels for break/continue
typedef struct LoopContext {
    char* start_label;  // For continue
    char* end_label;    // For break
    struct LoopContext* parent;
} LoopContext;

static LoopContext* loop_ctx_new(char* start, char* end, LoopContext* parent) {
    LoopContext* ctx = malloc(sizeof(LoopContext));
    ctx->start_label = start;
    ctx->end_label = end;
    ctx->parent = parent;
    return ctx;
}

// ============================================
// HELPER FUNCTIONS
// ============================================

// Create a label statement: (label name)
static Expr* make_label(const char* name) {
    // Represent as (call label name)
    Expr* label_func = expr_var("label", type_unit());
    
    ExprList* args = malloc(sizeof(ExprList));
    args->expr = expr_var(name, type_unit());
    args->next = NULL;
    
    return expr_apply(label_func, args, type_unit());
}

// Create a goto statement: (goto target)
static Expr* make_goto(const char* target) {
    // Represent as (call goto target)
    Expr* goto_func = expr_var("goto", type_unit());
    
    ExprList* args = malloc(sizeof(ExprList));
    args->expr = expr_var(target, type_unit());
    args->next = NULL;
    
    return expr_apply(goto_func, args, type_unit());
}

// Create an ifnot statement: (ifnot cond target)
static Expr* make_ifnot(Expr* cond, const char* target) {
    // Represent as (call ifnot cond target)
    Expr* ifnot_func = expr_var("ifnot", type_unit());
    
    ExprList* args = malloc(sizeof(ExprList));
    args->expr = cond;
    args->next = malloc(sizeof(ExprList));
    args->next->expr = expr_var(target, type_unit());
    args->next->next = NULL;
    
    return expr_apply(ifnot_func, args, type_unit());
}

// Append an expression to an expression list
static void append_expr(ExprList** list, Expr* expr) {
    ExprList* new_item = malloc(sizeof(ExprList));
    new_item->expr = expr;
    new_item->next = NULL;
    
    if (*list == NULL) {
        *list = new_item;
    } else {
        ExprList* cur = *list;
        while (cur->next) {
            cur = cur->next;
        }
        cur->next = new_item;
    }
}

// ============================================
// DESUGARING
// ============================================

// Forward declaration
static Expr* desugar_expr_with_context(Expr* expr, LoopContext* ctx);
static ExprList* desugar_statement_list_with_context(ExprList* stmts, LoopContext* ctx);

// Desugar a while loop:
//   (while cond body)
// becomes:
//   (label loop_start_N)
//   (set _cond_N bool cond)
//   (ifnot _cond_N loop_end_N)
//   body...
//   (goto loop_start_N)
//   (label loop_end_N)
static ExprList* desugar_while(Expr* while_expr, LoopContext* parent_ctx) {
    char* start_label = gen_label("loop_start");
    char* end_label = gen_label("loop_end");
    char* cond_var = gen_label("_cond");
    
    ExprList* result = NULL;
    
    // (label loop_start_N)
    append_expr(&result, make_label(start_label));
    
    // (set _cond_N bool cond)
    Expr* cond = desugar_expr_with_context(while_expr->data.while_loop.cond, parent_ctx);
    
    // Create set statement as (call set__cond_N cond)
    char set_func[128];
    snprintf(set_func, sizeof(set_func), "set_%s", cond_var);
    Expr* set_var = expr_var(set_func, type_unit());
    ExprList* set_args = malloc(sizeof(ExprList));
    set_args->expr = cond;
    set_args->next = NULL;
    Expr* set_stmt = expr_apply(set_var, set_args, type_bool());
    append_expr(&result, set_stmt);
    
    // (ifnot _cond_N loop_end_N)
    Expr* cond_var_ref = expr_var(cond_var, type_bool());
    append_expr(&result, make_ifnot(cond_var_ref, end_label));
    
    // body... (with break/continue context)
    LoopContext* loop_ctx = loop_ctx_new(start_label, end_label, parent_ctx);
    
    // If body is a seq, desugar its statements
    if (while_expr->data.while_loop.body->kind == EXPR_SEQ) {
        ExprList* body_stmts = desugar_statement_list_with_context(
            while_expr->data.while_loop.body->data.seq.exprs, 
            loop_ctx
        );
        
        // Append all body statements
        ExprList* cur = body_stmts;
        while (cur) {
            append_expr(&result, cur->expr);
            cur = cur->next;
        }
    } else {
        // Single statement body
        Expr* body = desugar_expr_with_context(while_expr->data.while_loop.body, loop_ctx);
        append_expr(&result, body);
    }
    
    free(loop_ctx);
    
    // (goto loop_start_N)
    append_expr(&result, make_goto(start_label));
    
    // (label loop_end_N)
    append_expr(&result, make_label(end_label));
    
    return result;
}

// Desugar an infinite loop:
//   (loop body)
// becomes:
//   (label loop_start_N)
//   body...
//   (goto loop_start_N)
//   (label loop_end_N)  // For break
static ExprList* desugar_loop(Expr* loop_expr, LoopContext* parent_ctx) {
    char* start_label = gen_label("loop_start");
    char* end_label = gen_label("loop_end");
    
    ExprList* result = NULL;
    
    // (label loop_start_N)
    append_expr(&result, make_label(start_label));
    
    // body... (with break/continue context)
    LoopContext* loop_ctx = loop_ctx_new(start_label, end_label, parent_ctx);
    
    // Note: EXPR_FOR is used for infinite loops in the current AST
    // If body is a seq, desugar its statements
    if (loop_expr->kind == EXPR_FOR && loop_expr->data.block.exprs) {
        ExprList* body_stmts = desugar_statement_list_with_context(
            loop_expr->data.block.exprs, 
            loop_ctx
        );
        
        // Append all body statements
        ExprList* cur = body_stmts;
        while (cur) {
            append_expr(&result, cur->expr);
            cur = cur->next;
        }
    }
    
    free(loop_ctx);
    
    // (goto loop_start_N)
    append_expr(&result, make_goto(start_label));
    
    // (label loop_end_N)
    append_expr(&result, make_label(end_label));
    
    return result;
}

// Desugar break: (break) becomes (goto loop_end_N)
static Expr* desugar_break(LoopContext* ctx) {
    if (!ctx) {
        fprintf(stderr, "Error: break outside of loop\n");
        exit(1);
    }
    return make_goto(ctx->end_label);
}

// Desugar continue: (continue) becomes (goto loop_start_N)
static Expr* desugar_continue(LoopContext* ctx) {
    if (!ctx) {
        fprintf(stderr, "Error: continue outside of loop\n");
        exit(1);
    }
    return make_goto(ctx->start_label);
}

// Desugar an if statement:
//   (if cond body)
// becomes:
//   (ifnot cond skip_N)
//   body...
//   (label skip_N)
static ExprList* desugar_if(Expr* if_expr, LoopContext* ctx) {
    char* skip_label = gen_label("if_skip");
    
    ExprList* result = NULL;
    
    // (ifnot cond skip_N)
    Expr* cond = desugar_expr_with_context(if_expr->data.if_expr.cond, ctx);
    append_expr(&result, make_ifnot(cond, skip_label));
    
    // body... (then branch)
    Expr* then_body = if_expr->data.if_expr.then_expr;
    if (then_body->kind == EXPR_SEQ) {
        ExprList* body_stmts = desugar_statement_list_with_context(
            then_body->data.seq.exprs, 
            ctx
        );
        
        // Append all body statements
        ExprList* cur = body_stmts;
        while (cur) {
            append_expr(&result, cur->expr);
            cur = cur->next;
        }
    } else {
        // Single statement body
        Expr* body = desugar_expr_with_context(then_body, ctx);
        append_expr(&result, body);
    }
    
    // (label skip_N)
    append_expr(&result, make_label(skip_label));
    
    return result;
}

// Desugar a single expression
static Expr* desugar_expr_with_context(Expr* expr, LoopContext* ctx) {
    if (!expr) return NULL;
    
    switch (expr->kind) {
        case EXPR_WHILE:
            // Can't return a statement list from here, caller must handle
            fprintf(stderr, "Error: while loop must be in statement context\n");
            exit(1);
            
        case EXPR_FOR:
            // Can't return a statement list from here, caller must handle
            fprintf(stderr, "Error: loop must be in statement context\n");
            exit(1);
            
        case EXPR_IF:
            // Can't return a statement list from here, caller must handle
            fprintf(stderr, "Error: if statement must be in statement context\n");
            exit(1);
            
        case EXPR_BREAK:
            return desugar_break(ctx);
            
        case EXPR_CONTINUE:
            return desugar_continue(ctx);
            
        case EXPR_SEQ: {
            // Desugar sequence of statements
            ExprList* desugared = desugar_statement_list_with_context(expr->data.seq.exprs, ctx);
            return expr_seq(desugared, expr->type);
        }
        
        case EXPR_APPLY: {
            // Recursively desugar arguments
            ExprList* new_args = NULL;
            ExprList* cur = expr->data.apply.args;
            while (cur) {
                Expr* desugared_arg = desugar_expr_with_context(cur->expr, ctx);
                append_expr(&new_args, desugared_arg);
                cur = cur->next;
            }
            
            return expr_apply(
                desugar_expr_with_context(expr->data.apply.func, ctx),
                new_args,
                expr->type
            );
        }
        
        case EXPR_LET: {
            // Desugar let body
            Expr* new_body = desugar_expr_with_context(expr->data.let.body, ctx);
            
            // Desugar binding values
            BindingList* new_bindings = NULL;
            BindingList* cur = expr->data.let.bindings;
            while (cur) {
                Binding* new_binding = malloc(sizeof(Binding));
                new_binding->name = cur->binding->name;
                new_binding->type = cur->binding->type;
                new_binding->value = desugar_expr_with_context(cur->binding->value, ctx);
                
                BindingList* new_item = malloc(sizeof(BindingList));
                new_item->binding = new_binding;
                new_item->next = new_bindings;
                new_bindings = new_item;
                
                cur = cur->next;
            }
            
            return expr_let(new_bindings, new_body, expr->type);
        }
        
        // Literals and other leaf nodes - return as-is
        default:
            return expr;
    }
}

// Desugar a statement list
static ExprList* desugar_statement_list_with_context(ExprList* stmts, LoopContext* ctx) {
    if (!stmts) return NULL;
    
    ExprList* result = NULL;
    ExprList* cur = stmts;
    
    while (cur) {
        Expr* stmt = cur->expr;
        
        if (stmt->kind == EXPR_WHILE) {
            // While loop expands to multiple statements
            ExprList* desugared = desugar_while(stmt, ctx);
            
            // Append all desugared statements
            ExprList* d = desugared;
            while (d) {
                append_expr(&result, d->expr);
                d = d->next;
            }
            
        } else if (stmt->kind == EXPR_FOR) {
            // Infinite loop expands to multiple statements
            ExprList* desugared = desugar_loop(stmt, ctx);
            
            // Append all desugared statements
            ExprList* d = desugared;
            while (d) {
                append_expr(&result, d->expr);
                d = d->next;
            }
            
        } else if (stmt->kind == EXPR_IF) {
            // If statement expands to multiple statements
            ExprList* desugared = desugar_if(stmt, ctx);
            
            // Append all desugared statements
            ExprList* d = desugared;
            while (d) {
                append_expr(&result, d->expr);
                d = d->next;
            }
            
        } else {
            // Regular statement - desugar recursively
            Expr* desugared = desugar_expr_with_context(stmt, ctx);
            append_expr(&result, desugared);
        }
        
        cur = cur->next;
    }
    
    return result;
}

// ============================================
// PUBLIC API
// ============================================

Expr* desugar_expr(Expr* expr) {
    return desugar_expr_with_context(expr, NULL);
}

ExprList* desugar_statement_list(ExprList* stmts) {
    return desugar_statement_list_with_context(stmts, NULL);
}

Module* desugar_module(Module* module) {
    if (!module) return NULL;
    
    // Desugar each function in the module
    DefList* cur_def = module->definitions;
    while (cur_def) {
        Definition* def = cur_def->def;
        
        if (def->kind == DEF_FUNCTION) {
            // Desugar function body
            def->data.func.body = desugar_expr(def->data.func.body);
        }
        
        cur_def = cur_def->next;
    }
    
    return module;
}
