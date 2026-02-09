#define _POSIX_C_SOURCE 200809L
#include "bytecode.h"
#include "parser.h"
#include "lexer.h"
#include "ast_export.h"
#include "desugar.h"
#include "module_loader.h"
#include "test_framework.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

typedef struct Local {
    char* name;
    uint32_t index;
    TypeKind type;  // Track variable type for type-directed dispatch
    struct Local* next;
} Local;

typedef struct FunctionInfo {
    char* name;
    uint32_t index;
    uint32_t param_count;
    struct FunctionInfo* next;
} FunctionInfo;

typedef struct PendingJump {
    uint32_t instruction_offset;
    char* target_label;  // Name of the label this jump targets
    struct PendingJump* next;
} PendingJump;

typedef struct LabelInfo {
    char* name;
    uint32_t position;  // Instruction offset
    struct LabelInfo* next;
} LabelInfo;

typedef struct LoopContext {
    uint32_t start_label;  // Label for continue (loop start)
    uint32_t end_label;    // Label for break (loop end)
    PendingJump* pending_breaks;  // List of break jumps to patch
    struct LoopContext* parent;  // For nested loops
} LoopContext;

typedef struct {
    BytecodeProgram* program;
    uint32_t current_function;
    Local* locals;
    uint32_t local_count;
    uint32_t max_local_count;
    FunctionInfo* functions;
    LoopContext* loop_stack;  // Stack of enclosing loops
    LabelInfo* labels;  // Map of label names to positions
    PendingJump* pending_jumps;  // Jumps that need patching
    Module* module;  // Module being compiled (for import checking)
    ModuleCache* module_cache;  // Cache for loaded modules
} Compiler;

void compile_expr(Compiler* comp, Expr* expr);

void compiler_init(Compiler* comp) {
    comp->program = bytecode_program_new();
    comp->current_function = 0;
    comp->locals = NULL;
    comp->local_count = 0;
    comp->max_local_count = 0;
    comp->functions = NULL;
    comp->loop_stack = NULL;  // Initialize loop stack
    comp->labels = NULL;  // Initialize label map
    comp->pending_jumps = NULL;  // Initialize pending jumps
    comp->module = NULL;  // Initialize module (set later in compile_module)
    comp->module_cache = module_cache_new();  // Initialize module cache
}

static void compiler_add_function(Compiler* comp, const char* name, uint32_t index, uint32_t param_count) {
    FunctionInfo* info = malloc(sizeof(FunctionInfo));
    info->name = strdup(name);
    info->index = index;
    info->param_count = param_count;
    info->next = comp->functions;
    comp->functions = info;
}

static bool compiler_find_function(Compiler* comp, const char* name, uint32_t* out_index, uint32_t* out_param_count) {
    FunctionInfo* current = comp->functions;
    while (current) {
        if (strcmp(current->name, name) == 0) {
            *out_index = current->index;
            if (out_param_count) {
                *out_param_count = current->param_count;
            }
            return true;
        }
        current = current->next;
    }
    return false;
}

static uint32_t compiler_add_local(Compiler* comp, const char* name, TypeKind type) {
    Local* local = malloc(sizeof(Local));
    local->name = strdup(name);
    local->type = type;
    local->index = comp->local_count++;
    local->next = comp->locals;
    comp->locals = local;
    if (comp->local_count > comp->max_local_count) {
        comp->max_local_count = comp->local_count;
    }
    return local->index;
}

static bool compiler_find_local(Compiler* comp, const char* name, uint32_t* out_index, TypeKind* out_type) {
    Local* current = comp->locals;
    while (current) {
        if (strcmp(current->name, name) == 0) {
            *out_index = current->index;
            if (out_type) {
                *out_type = current->type;
            }
            return true;
        }
        current = current->next;
    }
    return false;
}

// Helper to extract TypeKind from Type pointer
static TypeKind type_to_typekind(Type* type) {
    if (!type) return TYPE_UNIT;
    return type->kind;
}

// Helper to get typed operation name from short name and type
static const char* get_typed_operation(const char* short_name, TypeKind type) {
    // Map short names to typed operation names
    // For example: "add" + TYPE_INT -> "op_add_i64"
    
    // Use multiple buffers to avoid overwrites during nested compilation
    static char buffers[8][64];
    static int buffer_index = 0;
    char* buffer = buffers[buffer_index];
    buffer_index = (buffer_index + 1) % 8;
    
    // String operations (handle these first before type_suffix check)
    if (strcmp(short_name, "concat") == 0) return "string_concat";
    if (strcmp(short_name, "slice") == 0) return "string_slice";
    if (strcmp(short_name, "from_i64") == 0) return "string_from_i64";
    if (strcmp(short_name, "from_f64") == 0) return "string_from_f64";
    if (strcmp(short_name, "from_bool") == 0) return "string_from_bool";
    
    // I/O operations - handle BEFORE numeric check since print works on all types
    if (strcmp(short_name, "print") == 0) {
        switch (type) {
            case TYPE_INT: return "io_print_i64";    // int is always i64
            case TYPE_FLOAT: return "io_print_f64";  // float is always f64
            case TYPE_BOOL: return "io_print_bool";
            case TYPE_STRING: return "io_print_str";
            case TYPE_ARRAY: return "io_print_array";
            case TYPE_MAP: return "io_print_map";
            case TYPE_DECIMAL: return "io_print_decimal";
            default: return "io_print_i64";
        }
    }
    
    // Length operation - could be array or string, need context
    if (strcmp(short_name, "len") == 0) {
        if (type == TYPE_STRING) return "string_length";
        return "array_length";
    }
    
    // Array operations (type-agnostic in VM, but keep existing names)
    if (strcmp(short_name, "push") == 0) return "array_push";
    if (strcmp(short_name, "get") == 0) return "array_get";
    if (strcmp(short_name, "set") == 0) return "array_set";
    
    const char* type_suffix = "";
    
    switch (type) {
        case TYPE_INT: type_suffix = "_i64"; break;    // int is always i64
        case TYPE_FLOAT: type_suffix = "_f64"; break;  // float is always f64
        case TYPE_DECIMAL: type_suffix = "_decimal"; break;
        default:
            // Not a numeric type, return original name
            return short_name;
    }
    
    // Check if this is a polymorphic operation
    if (strcmp(short_name, "add") == 0 ||
        strcmp(short_name, "sub") == 0 ||
        strcmp(short_name, "mul") == 0 ||
        strcmp(short_name, "div") == 0 ||
        strcmp(short_name, "mod") == 0 ||
        strcmp(short_name, "neg") == 0) {
        snprintf(buffer, 64, "op_%s%s", short_name, type_suffix);
        return buffer;
    }
    
    if (strcmp(short_name, "eq") == 0 ||
        strcmp(short_name, "ne") == 0 ||
        strcmp(short_name, "lt") == 0 ||
        strcmp(short_name, "gt") == 0 ||
        strcmp(short_name, "le") == 0 ||
        strcmp(short_name, "ge") == 0) {
        snprintf(buffer, 64, "op_%s%s", short_name, type_suffix);
        return buffer;
    }
    
    if (strcmp(short_name, "abs") == 0 ||
        strcmp(short_name, "min") == 0 ||
        strcmp(short_name, "max") == 0 ||
        strcmp(short_name, "sqrt") == 0 ||
        strcmp(short_name, "pow") == 0) {
        snprintf(buffer, 64, "math_%s%s", short_name, type_suffix);
        return buffer;
    }
    
    // Not a polymorphic operation, return as-is
    return short_name;
}

void compile_lit_int(Compiler* comp, Expr* expr) {
    Instruction inst = {
        .opcode = OP_PUSH_INT,
        .operand.int_val = expr->data.int_val
    };
    bytecode_emit(comp->program, inst);
}

void compile_lit_string(Compiler* comp, Expr* expr) {
    uint32_t str_idx = bytecode_add_string(comp->program, expr->data.string_val);
    Instruction inst = {
        .opcode = OP_PUSH_STRING,
        .operand.uint_val = str_idx
    };
    bytecode_emit(comp->program, inst);
}

void compile_lit_float(Compiler* comp, Expr* expr) {
    // For now, use F64 for all float literals
    Instruction inst = {
        .opcode = OP_PUSH_FLOAT,
        .operand.float_val = expr->data.float_val
    };
    bytecode_emit(comp->program, inst);
}

void compile_lit_bool(Compiler* comp, Expr* expr) {
    Instruction inst = {
        .opcode = OP_PUSH_BOOL,
        .operand = {.int_val = 0}  // Zero-initialize union first
    };
    inst.operand.bool_val = expr->data.bool_val;  // Then set bool value
    bytecode_emit(comp->program, inst);
}

void compile_lit_unit(Compiler* comp) {
    Instruction inst = {.opcode = OP_PUSH_UNIT};
    bytecode_emit(comp->program, inst);
}

void compile_var(Compiler* comp, Expr* expr) {
    uint32_t index = 0;
    if (!compiler_find_local(comp, expr->data.var.name, &index, NULL)) {
        fprintf(stderr, "Undefined local: %s\n", expr->data.var.name);
        exit(1);
    }
    Instruction inst = {
        .opcode = OP_LOAD_LOCAL,
        .operand.uint_val = index
    };
    bytecode_emit(comp->program, inst);
}

void compile_binary(Compiler* comp, Expr* expr) {
    compile_expr(comp, expr->data.binary.left);
    compile_expr(comp, expr->data.binary.right);

    Instruction inst;
    switch (expr->data.binary.op) {
        case BIN_ADD:
            inst.opcode = OP_ADD_INT;
            break;
        case BIN_SUB:
            inst.opcode = OP_SUB_INT;
            break;
        case BIN_MUL:
            inst.opcode = OP_MUL_INT;
            break;
        case BIN_DIV:
            inst.opcode = OP_DIV_INT;
            break;
        case BIN_EQ:
            inst.opcode = OP_EQ_INT;
            break;
        case BIN_LT:
            inst.opcode = OP_LT_INT;
            break;
        case BIN_GT:
            inst.opcode = OP_GT_INT;
            break;
        case BIN_LTE:
            inst.opcode = OP_LTE_INT;
            break;
        case BIN_GTE:
            inst.opcode = OP_GTE_INT;
            break;
        default:
            fprintf(stderr, "Unsupported binary operation\n");
            exit(1);
    }

    bytecode_emit(comp->program, inst);
}

void compile_seq(Compiler* comp, Expr* expr) {
    ExprList* current = expr->data.seq.exprs;
    while (current) {
        compile_expr(comp, current->expr);
        if (current->next) {
            // Pop intermediate results except the last one
            Instruction pop = {.opcode = OP_POP};
            bytecode_emit(comp->program, pop);
        }
        current = current->next;
    }
}

static uint32_t compile_args(Compiler* comp, ExprList* args) {
    uint32_t count = 0;
    ExprList* current = args;
    while (current) {
        compile_expr(comp, current->expr);
        count++;
        current = current->next;
    }
    return count;
}

void compile_apply(Compiler* comp, Expr* expr) {
    Expr* func = expr->data.apply.func;
    if (func->kind != EXPR_VAR) {
        fprintf(stderr, "Only direct function calls are supported\n");
        exit(1);
    }

    const char* name = func->data.var.name;
    
    // Skip module checking for:
    // 1. Core IR constructs (label, goto, ifnot)
    // Module checking removed - functions are resolved at link time after
    // compiling imported modules. If a function doesn't exist, compilation
    // will fail naturally when trying to call it.

    // Type-directed dispatch for polymorphic operations
    // Check if this is a short polymorphic operation (add, sub, mul, etc.)
    if (strcmp(name, "add") == 0 || strcmp(name, "sub") == 0 || 
        strcmp(name, "mul") == 0 || strcmp(name, "div") == 0 ||
        strcmp(name, "mod") == 0 || strcmp(name, "neg") == 0 ||
        strcmp(name, "eq") == 0 || strcmp(name, "ne") == 0 ||
        strcmp(name, "lt") == 0 || strcmp(name, "gt") == 0 ||
        strcmp(name, "le") == 0 || strcmp(name, "ge") == 0 ||
        strcmp(name, "abs") == 0 || strcmp(name, "min") == 0 ||
        strcmp(name, "max") == 0 || strcmp(name, "sqrt") == 0 ||
        strcmp(name, "pow") == 0 ||
        strcmp(name, "print") == 0 || strcmp(name, "len") == 0 ||
        strcmp(name, "push") == 0 || strcmp(name, "get") == 0 ||
        strcmp(name, "set") == 0 || strcmp(name, "concat") == 0 ||
        strcmp(name, "slice") == 0 || strcmp(name, "from_i64") == 0 ||
        strcmp(name, "from_f64") == 0 || strcmp(name, "from_bool") == 0) {
        
        // Get type from first argument
        if (!expr->data.apply.args) {
            fprintf(stderr, "Operation '%s' requires at least one argument\n", name);
            exit(1);
        }
        
        // Check if first argument is a variable reference
        Expr* first_arg = expr->data.apply.args->expr;
        TypeKind arg_type = TYPE_INT;  // Default to int (i64) if type can't be determined
        
        if (first_arg->kind == EXPR_VAR) {
            // Look up variable type
            uint32_t dummy_idx;
            if (!compiler_find_local(comp, first_arg->data.var.name, &dummy_idx, &arg_type)) {
                fprintf(stderr, "Undefined variable in operation: %s\n", first_arg->data.var.name);
                exit(1);
            }
        } else if (first_arg->kind == EXPR_LIT_INT) {
            // Integer literal defaults to int (i64)
            arg_type = TYPE_INT;
        } else if (first_arg->kind == EXPR_LIT_FLOAT) {
            // Float literal defaults to float (f64)
            arg_type = TYPE_FLOAT;
        } else if (first_arg->kind == EXPR_LIT_STRING) {
            // String literal
            arg_type = TYPE_STRING;
        } else if (first_arg->kind == EXPR_LIT_BOOL) {
            // Boolean literal
            arg_type = TYPE_BOOL;
        } else if (first_arg->kind == EXPR_APPLY) {
            // Nested function call - infer return type
            if (first_arg->data.apply.func && first_arg->data.apply.func->kind == EXPR_VAR) {
                const char* func_name = first_arg->data.apply.func->data.var.name;
                // Comparison operations return bool
                if (strcmp(func_name, "lt") == 0 || strcmp(func_name, "gt") == 0 ||
                    strcmp(func_name, "le") == 0 || strcmp(func_name, "ge") == 0 ||
                    strcmp(func_name, "eq") == 0 || strcmp(func_name, "ne") == 0) {
                    arg_type = TYPE_BOOL;
                }
                // Otherwise default to int for arithmetic operations
            }
        } else if (first_arg->type) {
            // Use type from expression
            arg_type = type_to_typekind(first_arg->type);
            // If we got TYPE_UNIT (unknown type from nested expr), default to TYPE_INT
            // But preserve TYPE_STRING and other known types
            if (arg_type == TYPE_UNIT) {
                arg_type = TYPE_INT;
            }
        }
        // Otherwise use default TYPE_INT
        
        // Map to typed operation
        const char* typed_name = get_typed_operation(name, arg_type);
        
        // Replace name with typed version and continue with normal compilation
        name = typed_name;
    }

    // Boolean operations - always operate on bool type
    if (strcmp(name, "and") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "and expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_AND_BOOL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "or") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "or expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_OR_BOOL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "not") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "not expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NOT_BOOL};
        bytecode_emit(comp->program, inst);
        return;
    }

    // AISL-Core: label, goto, ifnot (desugared from Agent constructs)
    // (label name) - Create a jump target
    if (strcmp(name, "label") == 0) {
        // Get label name from argument
        if (!expr->data.apply.args || expr->data.apply.args->next) {
            fprintf(stderr, "label expects exactly 1 argument\n");
            exit(1);
        }
        
        // Extract label name (it's a variable reference)
        Expr* label_arg = expr->data.apply.args->expr;
        if (label_arg->kind != EXPR_VAR) {
            fprintf(stderr, "label argument must be a name\n");
            exit(1);
        }
        
        char* label_name = label_arg->data.var.name;
        uint32_t position = comp->program->instruction_count;
        
        // Add to label map
        LabelInfo* info = malloc(sizeof(LabelInfo));
        info->name = strdup(label_name);
        info->position = position;
        info->next = comp->labels;
        comp->labels = info;
        
        // Labels don't emit bytecode - they just mark positions
        // But we need to push unit for expression evaluation
        Instruction unit = {.opcode = OP_PUSH_UNIT};
        bytecode_emit(comp->program, unit);
        return;
    }
    
    // (goto target) - Unconditional jump
    if (strcmp(name, "goto") == 0) {
        // Get target label name
        if (!expr->data.apply.args || expr->data.apply.args->next) {
            fprintf(stderr, "goto expects exactly 1 argument (label name)\n");
            exit(1);
        }
        
        Expr* target_arg = expr->data.apply.args->expr;
        if (target_arg->kind != EXPR_VAR) {
            fprintf(stderr, "goto target must be a label name\n");
            exit(1);
        }
        
        char* target_name = target_arg->data.var.name;
        
        // Emit jump with placeholder offset
        Instruction jump = {.opcode = OP_JUMP, .operand.jump.target = 0xFFFFFFFF};
        uint32_t offset = bytecode_emit(comp->program, jump);
        
        // Add to pending jumps
        PendingJump* pending = malloc(sizeof(PendingJump));
        pending->instruction_offset = offset;
        pending->target_label = strdup(target_name);
        pending->next = comp->pending_jumps;
        comp->pending_jumps = pending;
        
        // Push unit for expression evaluation
        Instruction unit = {.opcode = OP_PUSH_UNIT};
        bytecode_emit(comp->program, unit);
        
        return;
    }
    
    // (ifnot cond target) - Conditional jump
    if (strcmp(name, "ifnot") == 0) {
        if (!expr->data.apply.args || !expr->data.apply.args->next || expr->data.apply.args->next->next) {
            fprintf(stderr, "ifnot expects exactly 2 arguments (condition, label)\n");
            exit(1);
        }
        
        // Compile condition
        Expr* cond = expr->data.apply.args->expr;
        compile_expr(comp, cond);
        
        // Get target label
        Expr* target_arg = expr->data.apply.args->next->expr;
        if (target_arg->kind != EXPR_VAR) {
            fprintf(stderr, "ifnot target must be a label name\n");
            exit(1);
        }
        
        char* target_name = target_arg->data.var.name;
        
        // Emit conditional jump (jump if false/zero)
        Instruction jfalse = {.opcode = OP_JUMP_IF_FALSE, .operand.jump.target = 0xFFFFFFFF};
        uint32_t offset = bytecode_emit(comp->program, jfalse);
        
        // Add to pending jumps
        PendingJump* pending = malloc(sizeof(PendingJump));
        pending->instruction_offset = offset;
        pending->target_label = strdup(target_name);
        pending->next = comp->pending_jumps;
        comp->pending_jumps = pending;
        
        // Push unit for expression evaluation
        Instruction unit = {.opcode = OP_PUSH_UNIT};
        bytecode_emit(comp->program, unit);
        
        return;
    }

    // V4.0 Variable declarations: (set varname value) becomes set_varname(value)
    if (strncmp(name, "set_", 4) == 0) {
        const char* var_name = name + 4;  // Skip "set_" prefix
        
        // Compile the value expression
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "Variable assignment expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        
        // Extract type from the value expression
        TypeKind var_type = type_to_typekind(expr->data.apply.args->expr->type);
        
        // Check if variable already exists
        uint32_t index = 0;
        if (!compiler_find_local(comp, var_name, &index, NULL)) {
            // Variable doesn't exist, create it
            index = compiler_add_local(comp, var_name, var_type);
        }
        
        // Emit STORE_LOCAL
        Instruction inst = {.opcode = OP_STORE_LOCAL, .operand.uint_val = index};
        bytecode_emit(comp->program, inst);
        
        // Push unit value (assignments return unit)
        Instruction unit = {.opcode = OP_PUSH_UNIT};
        bytecode_emit(comp->program, unit);
        return;
    }

    // V4.0 Conditional expressions: if_i32, if_i64, if_f32, if_f64, if_string
    // Syntax: (call if_i32 condition then_value else_value)
    if (strcmp(name, "if_i64") == 0 || strcmp(name, "if_f64") == 0 ||
        strcmp(name, "if_string") == 0) {
        
        // Validate args: condition, then_expr, else_expr
        ExprList* args = expr->data.apply.args;
        if (!args || !args->next || !args->next->next || args->next->next->next != NULL) {
            fprintf(stderr, "%s expects exactly 3 arguments (condition, then, else)\n", name);
            exit(1);
        }
        
        // Compile condition
        compile_expr(comp, args->expr);
        
        // Jump to else if condition is false
        Instruction jump_if_false = {.opcode = OP_JUMP_IF_FALSE};
        uint32_t jump_to_else_idx = bytecode_emit(comp->program, jump_if_false);
        
        // Compile then branch
        compile_expr(comp, args->next->expr);
        
        // Jump over else branch
        Instruction jump_over_else = {.opcode = OP_JUMP};
        uint32_t jump_over_else_idx = bytecode_emit(comp->program, jump_over_else);
        
        // Patch jump_to_else to point here (start of else branch)
        uint32_t else_start = comp->program->instruction_count;
        bytecode_patch_jump(comp->program, jump_to_else_idx, else_start);
        
        // Compile else branch
        compile_expr(comp, args->next->next->expr);
        
        // Patch jump_over_else to point here (after else)
        uint32_t after_else = comp->program->instruction_count;
        bytecode_patch_jump(comp->program, jump_over_else_idx, after_else);
        
        return;
    }

    // V4.0 While loops: while_loop(condition, body)
    // Syntax: (call while_loop condition body)
    if (strcmp(name, "while_loop") == 0) {
        // Validate args: condition, body
        ExprList* args = expr->data.apply.args;
        if (!args || !args->next || args->next->next != NULL) {
            fprintf(stderr, "while_loop expects exactly 2 arguments (condition, body)\n");
            exit(1);
        }
        
        // Remember loop start position
        uint32_t loop_start = comp->program->instruction_count;
        
        // Compile condition
        compile_expr(comp, args->expr);
        
        // Jump to end if condition is false
        Instruction jump_if_false = {.opcode = OP_JUMP_IF_FALSE};
        uint32_t jump_to_end_idx = bytecode_emit(comp->program, jump_if_false);
        
        // Pop the condition result (it's consumed by JUMP_IF_FALSE, but we need to pop for cleanliness)
        // Actually JUMP_IF_FALSE pops the value, so no need to pop here
        
        // Compile body
        compile_expr(comp, args->next->expr);
        
        // Pop body result (loops don't produce values)
        Instruction pop = {.opcode = OP_POP};
        bytecode_emit(comp->program, pop);
        
        // Jump back to loop start
        Instruction jump_to_start = {.opcode = OP_JUMP, .operand.jump.target = loop_start};
        bytecode_emit(comp->program, jump_to_start);
        
        // Patch jump_to_end to point here (after loop)
        uint32_t loop_end = comp->program->instruction_count;
        bytecode_patch_jump(comp->program, jump_to_end_idx, loop_end);
        
        // Push unit (while returns unit)
        Instruction unit = {.opcode = OP_PUSH_UNIT};
        bytecode_emit(comp->program, unit);
        
        return;
    }
    
    // Sequence operation - executes multiple expressions in order
    // Syntax: (call seq expr1 expr2 expr3 ...)
    // Returns the value of the last expression
    if (strcmp(name, "seq") == 0) {
        ExprList* args = expr->data.apply.args;
        if (!args) {
            // Empty sequence returns unit
            Instruction unit = {.opcode = OP_PUSH_UNIT};
            bytecode_emit(comp->program, unit);
            return;
        }
        
        // Compile each expression
        while (args) {
            compile_expr(comp, args->expr);
            if (args->next) {
                // Pop intermediate results except the last one
                Instruction pop = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop);
            }
            args = args->next;
        }
        return;
    }

    // V3.0 Builtins - print_int for compatibility
    if (strcmp(name, "print_int") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "print_int expects exactly 1 argument\n");
            exit(1);
        }
        // Just print the int (simplified for now)
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_DEBUG};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed print builtins (v6.0 - removed i32/f32, kept i64/f64 which are now int/float)
    if (strcmp(name, "io_print_i64") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_i64 expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // V4.0 Typed print builtins (v6.0 - removed f32, kept f64 which is now float)
    if (strcmp(name, "io_print_f64") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_f64 expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "io_print_bool") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_bool expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_BOOL};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "io_print_str") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_str expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_STR};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "io_print_array") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_array expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_ARRAY};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "io_print_map") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_map expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_MAP};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "io_print_decimal") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_decimal expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 File I/O operations
    if (strcmp(name, "io_file_open") == 0) {
        // io_file_open(path: string, mode: i32) -> i32 (file descriptor)
        // mode: 0 = read, 1 = write, 2 = append, 3 = read+write
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "io_file_open expects 2 arguments (path: string, mode: i32)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_IO_OPEN};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "io_file_read") == 0) {
        // io_file_read(handle: i32) -> string
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "io_file_read expects 1 argument (handle: i32)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_IO_READ};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "io_file_write") == 0) {
        // io_file_write(handle: i32, data: string) -> unit
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "io_file_write expects 2 arguments (handle: i32, data: string)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_IO_WRITE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "io_file_close") == 0) {
        // io_file_close(handle: i32) -> unit
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "io_file_close expects 1 argument (handle: i32)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_IO_CLOSE};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed arithmetic operations - i64 (int is always i64 in AISL)
    if (strcmp(name, "op_add_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_add_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ADD_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_sub_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_sub_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SUB_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_mul_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_mul_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MUL_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_div_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_div_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIV_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_mod_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_mod_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MOD_I64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed arithmetic operations - f64 (float is always f64 in AISL)
    if (strcmp(name, "op_add_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_add_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ADD_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_sub_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_sub_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SUB_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_mul_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_mul_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MUL_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_div_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_div_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIV_F64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed negation operations
    if (strcmp(name, "op_neg_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "op_neg_i64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NEG_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_neg_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "op_neg_f64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NEG_F64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // Decimal arithmetic operations
    if (strcmp(name, "op_add_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_add_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ADD_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_sub_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_sub_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SUB_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_mul_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_mul_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MUL_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_div_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_div_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIV_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_neg_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "op_neg_decimal expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NEG_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed comparison operations - i64 (int is always i64 in AISL)
    if (strcmp(name, "op_eq_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_eq_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ne_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ne_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NE_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_lt_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_lt_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LT_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_gt_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_gt_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GT_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_le_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_le_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LE_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ge_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ge_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GE_I64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed comparison operations - f64 (float is always f64 in AISL)
    if (strcmp(name, "op_eq_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_eq_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ne_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ne_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NE_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_lt_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_lt_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LT_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_gt_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_gt_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GT_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_le_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_le_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LE_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ge_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ge_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GE_F64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // Decimal comparison operations
    if (strcmp(name, "op_eq_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_eq_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ne_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ne_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NE_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_lt_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_lt_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LT_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_gt_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_gt_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GT_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_le_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_le_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LE_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ge_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ge_decimal expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GE_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Type conversion operations (only i64/f64, no i32/f32)
    if (strcmp(name, "cast_i64_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i64_f64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I64_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_f64_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_f64_i64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_F64_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // Decimal conversions
    if (strcmp(name, "cast_int_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_int_decimal expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_INT_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_decimal_int") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_decimal_int expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_DECIMAL_INT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_float_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_float_decimal expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_FLOAT_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_decimal_float") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_decimal_float expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_DECIMAL_FLOAT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "string_from_decimal") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_from_decimal expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_FROM_DECIMAL};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    
    // Math functions
    if (strcmp(name, "math_sqrt") == 0 || strcmp(name, "math_sqrt_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "math_sqrt expects 1 argument (f64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_SQRT_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_pow") == 0 || strcmp(name, "math_pow_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_pow expects 2 arguments (base f64, exp f64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_POW_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_abs_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "math_abs_i64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_ABS_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_abs_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "math_abs_f64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_ABS_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_min_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_min_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MIN_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_min_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_min_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MIN_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_max_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_max_i64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MAX_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_max_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_max_f64 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MAX_F64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 String operations (explicit typed versions)
    if (strcmp(name, "string_new") == 0) {
        // string_new(char_array) - creates string from literal
        // Actually, strings are already created from literals, so this is mainly for compatibility
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_new expects 1 argument\n");
            exit(1);
        }
        // Just pass through - the argument is already a string
        return;
    }
    
    if (strcmp(name, "string_concat") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_concat expects 2 arguments (str1, str2)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_CONCAT};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_length") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_length expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_LEN};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_slice") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "string_slice expects 3 arguments (str, start, length)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_SLICE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_get") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_get expects 2 arguments (str, index)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_GET};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_equals") == 0) {
        // String equality comparison
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_equals expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_STR};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.1 String conversion operations (only i64/f64)
    if (strcmp(name, "string_from_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_from_i64 expects 1 argument (i64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_FROM_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_from_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_from_f64 expects 1 argument (f64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_FROM_F64};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.2 Advanced String operations - REMOVED
    // Now implemented in stdlib/core/string_utils.aisl
    // Use: (import string_utils) then call split, trim, contains, etc.

    
    if (strcmp(name, "array_new") == 0) {
        int arg_count = compile_args(comp, expr->data.apply.args);
        if (arg_count != 0) {
            fprintf(stderr, "array_new expects 0 arguments - arrays are always dynamic\n");
            exit(1);
        }
        // Push default capacity of 16
        Instruction push_cap = {
            .opcode = OP_PUSH_INT,
            .operand.int_val = 16
        };
        bytecode_emit(comp->program, push_cap);
        Instruction inst = {.opcode = OP_ARRAY_NEW};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "array_push") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "array_push expects 2 arguments (array, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_PUSH};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "array_get") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "array_get expects 2 arguments (array, index)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_GET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "array_set") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "array_set expects 3 arguments (array, index, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_SET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "array_length") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "array_length expects 1 argument (array)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_LEN};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // V4.0 Map operations (explicit typed versions)
    if (strcmp(name, "map_new") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "map_new expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_NEW};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "map_set") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "map_set expects 3 arguments (map, key, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_SET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "map_get") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "map_get expects 2 arguments (map, key)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_GET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "map_has") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "map_has expects 2 arguments (map, key)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_HAS};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "map_delete") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "map_delete expects 2 arguments (map, key)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_DELETE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "map_length") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "map_length expects 1 argument (map)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_LEN};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "map_keys") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "map_keys expects 1 argument (map)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MAP_KEYS};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // JSON operations (v4.4) - REMOVED
    // Now implemented in stdlib/data/json.aisl using map primitives
    // Use: (import json) then call parse, stringify, etc.
    
    // FFI (Foreign Function Interface) Operations
    
    if (strcmp(name, "ffi_load") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ffi_load expects 1 argument (library name)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FFI_LOAD};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "ffi_call") == 0) {
        // Compile: handle, function_name, arg1, arg2, ..., argN
        // Need at least handle + function_name
        int arg_count = compile_args(comp, expr->data.apply.args);
        if (arg_count < 2) {
            fprintf(stderr, "ffi_call expects at least 2 arguments (handle, function_name)\n");
            exit(1);
        }
        
        // Push argument count (excluding handle and function_name)
        Instruction count_inst = {.opcode = OP_PUSH_INT, .operand.int_val = arg_count - 2};
        bytecode_emit(comp->program, count_inst);
        
        Instruction inst = {.opcode = OP_FFI_CALL};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "ffi_available") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ffi_available expects 1 argument (library name)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FFI_AVAILABLE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "ffi_close") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ffi_close expects 1 argument (handle)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FFI_CLOSE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // HTTP Operations
    
    
    if (strcmp(name, "file_read") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "file_read expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_READ};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_write") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "file_write expects 2 arguments (path, content)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_WRITE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_append") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "file_append expects 2 arguments (path, content)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_APPEND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_exists") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "file_exists expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_EXISTS};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_delete") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "file_delete expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_DELETE};
        bytecode_emit(comp->program, inst);
        return;
    }

    // Standard Input
    if (strcmp(name, "stdin_read") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "stdin_read takes no arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STDIN_READ};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "stdin_read_all") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "stdin_read_all takes no arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STDIN_READ_ALL};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // Result type operations (result_ok, result_err) - REMOVED
    // Now implemented in stdlib/core/result.aisl using map primitives
    // Use: (import result) then call ok, err, is_ok, is_err, unwrap, etc.
    // Note: 'ok' and 'err' are now regular functions, not reserved keywords
    
    
    if (strcmp(name, "file_size") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "file_size expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_SIZE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_mtime") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "file_mtime expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_MTIME};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "dir_list") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "dir_list expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIR_LIST};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "dir_create") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "dir_create expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIR_CREATE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "dir_delete") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "dir_delete expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIR_DELETE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "regex_compile") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "regex_compile expects 1 argument (pattern)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_REGEX_COMPILE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "regex_match") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "regex_match expects 2 arguments (regex, text)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_REGEX_MATCH};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "regex_find") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "regex_find expects 2 arguments (regex, text)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_REGEX_FIND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "regex_find_all") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "regex_find_all expects 2 arguments (regex, text)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_REGEX_FIND_ALL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "regex_replace") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "regex_replace expects 3 arguments (regex, text, replacement)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_REGEX_REPLACE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "sha256") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "sha256 expects 1 argument (input)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CRYPTO_SHA256};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "md5") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "md5 expects 1 argument (input)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CRYPTO_MD5};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "hmac_sha256") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "hmac_sha256 expects 2 arguments (key, message)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CRYPTO_HMAC_SHA256};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // Base64 operations - REMOVED
    // Now implemented in stdlib/data/base64.aisl using pure AISL
    // Use: (import base64) then call encode, decode
    
    if (strcmp(name, "time_now") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "time_now expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TIME_NOW};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "time_format") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "time_format expects 2 arguments (timestamp, format)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TIME_FORMAT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "time_parse") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "time_parse expects 2 arguments (time_str, format)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TIME_PARSE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // SQLITE DATABASE OPERATIONS
    
    
    // WEBSOCKET OPERATIONS
    
    
    // PROCESS MANAGEMENT OPERATIONS
    
    if (strcmp(name, "process_spawn") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "process_spawn expects 2 arguments (command, args)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_SPAWN};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "process_exec") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "process_exec expects 2 arguments (command, args)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_EXEC};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "process_wait") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "process_wait expects 1 argument (process)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_WAIT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "process_kill") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "process_kill expects 2 arguments (process, signal)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_KILL};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "process_pipe") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "process_pipe expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_PIPE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "process_read") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "process_read expects 1 argument (process)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_READ};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "process_write") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "process_write expects 2 arguments (process, data)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_PROCESS_WRITE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // NETWORK SOCKET OPERATIONS
    
    if (strcmp(name, "tcp_listen") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "tcp_listen expects 1 argument (port)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_LISTEN};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "tcp_accept") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "tcp_accept expects 1 argument (server_socket)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_ACCEPT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "tcp_connect") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "tcp_connect expects 2 arguments (host, port)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_CONNECT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "tcp_tls_connect") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "tcp_tls_connect expects 2 arguments (host, port)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_TLS_CONNECT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "tcp_send") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "tcp_send expects 2 arguments (socket, data)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_SEND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "tcp_receive") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "tcp_receive expects 2 arguments (socket, max_bytes)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_RECEIVE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "tcp_close") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "tcp_close expects 1 argument (socket)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_TCP_CLOSE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "udp_socket") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "udp_socket expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_UDP_SOCKET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "udp_bind") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "udp_bind expects 2 arguments (socket, port)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_UDP_BIND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "udp_send_to") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 4) {
            fprintf(stderr, "udp_send_to expects 4 arguments (socket, data, host, port)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_UDP_SEND_TO};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "udp_receive_from") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "udp_receive_from expects 2 arguments (socket, max_bytes)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_UDP_RECEIVE_FROM};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // CHANNEL OPERATIONS (Thread-Safe Queues)
    
    if (strcmp(name, "channel_new") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "channel_new expects 1 argument (capacity)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CHANNEL_NEW};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "channel_send") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "channel_send expects 2 arguments (channel, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CHANNEL_SEND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "channel_recv") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "channel_recv expects 1 argument (channel)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CHANNEL_RECV};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // GARBAGE COLLECTION OPERATIONS
    
    if (strcmp(name, "gc_collect") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "gc_collect expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GC_COLLECT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "gc_stats") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "gc_stats expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GC_STATS};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "ArrayNew") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ArrayNew expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_NEW};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ArrayPush") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "ArrayPush expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_PUSH};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ArrayGet") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "ArrayGet expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_GET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ArraySet") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "ArraySet expects 3 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_SET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ArrayLen") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ArrayLen expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ARRAY_LEN};
        bytecode_emit(comp->program, inst);
        return;
    }

    uint32_t func_idx = 0;
    uint32_t param_count = 0;
    if (!compiler_find_function(comp, name, &func_idx, &param_count)) {
        fprintf(stderr, "Unknown function: %s\n", name);
        exit(1);
    }

    uint32_t arg_count = compile_args(comp, expr->data.apply.args);
    Instruction inst = {
        .opcode = OP_CALL,
        .operand.call.func_idx = func_idx
    };
    inst.operand.call.arg_count = arg_count;
    bytecode_emit(comp->program, inst);
}

void compile_let(Compiler* comp, Expr* expr) {
    Local* saved_locals = comp->locals;
    uint32_t saved_count = comp->local_count;

    BindingList* current = expr->data.let.bindings;
    while (current) {
        compile_expr(comp, current->binding->value);
        TypeKind binding_type = type_to_typekind(current->binding->type);
        uint32_t idx = compiler_add_local(comp, current->binding->name, binding_type);
        Instruction store = {.opcode = OP_STORE_LOCAL, .operand.uint_val = idx};
        bytecode_emit(comp->program, store);
        current = current->next;
    }

    compile_expr(comp, expr->data.let.body);

    comp->locals = saved_locals;
    comp->local_count = saved_count;
}

void compile_while(Compiler* comp, Expr* expr) {
    uint32_t start = comp->program->instruction_count;
    compile_expr(comp, expr->data.while_loop.cond);

    Instruction jfalse = {.opcode = OP_JUMP_IF_FALSE};
    uint32_t jfalse_offset = bytecode_emit(comp->program, jfalse);

    // Push loop context for break/continue
    LoopContext loop_ctx;
    loop_ctx.start_label = start;
    loop_ctx.end_label = 0;  // Will be set after body
    loop_ctx.pending_breaks = NULL;  // Initialize pending breaks list
    loop_ctx.parent = comp->loop_stack;
    comp->loop_stack = &loop_ctx;

    compile_expr(comp, expr->data.while_loop.body);

    // Pop loop context
    comp->loop_stack = loop_ctx.parent;

    Instruction jump = {.opcode = OP_JUMP, .operand.jump.target = start};
    bytecode_emit(comp->program, jump);

    uint32_t end = comp->program->instruction_count;
    bytecode_patch_jump(comp->program, jfalse_offset, end);
    
    // Patch all pending break jumps
    PendingJump* pending = loop_ctx.pending_breaks;
    while (pending) {
        bytecode_patch_jump(comp->program, pending->instruction_offset, end);
        PendingJump* next = pending->next;
        free(pending);
        pending = next;
    }
}

void compile_io_write(Compiler* comp, Expr* expr) {
    compile_expr(comp, expr->data.io_write.handle);
    compile_expr(comp, expr->data.io_write.data);

    Instruction inst = {.opcode = OP_IO_WRITE};
    bytecode_emit(comp->program, inst);
}

void compile_io_read(Compiler* comp, Expr* expr) {
    compile_expr(comp, expr->data.io_read.handle);
    Instruction inst = {.opcode = OP_IO_READ};
    bytecode_emit(comp->program, inst);
}

void compile_io_open(Compiler* comp, Expr* expr) {
    compile_expr(comp, expr->data.io_open.path);
    compile_expr(comp, expr->data.io_open.mode);
    Instruction inst = {.opcode = OP_IO_OPEN};
    bytecode_emit(comp->program, inst);
}

void compile_io_close(Compiler* comp, Expr* expr) {
    compile_expr(comp, expr->data.io_close.handle);
    Instruction inst = {.opcode = OP_IO_CLOSE};
    bytecode_emit(comp->program, inst);
}

void compile_if(Compiler* comp, Expr* expr) {
    // Compile condition
    compile_expr(comp, expr->data.if_expr.cond);
    
    // Jump to else branch if condition is false
    Instruction jump_if_false = {.opcode = OP_JUMP_IF_FALSE};
    uint32_t jump_to_else_idx = bytecode_emit(comp->program, jump_if_false);
    
    // Compile then branch
    compile_expr(comp, expr->data.if_expr.then_expr);
    
    // Jump over else branch
    Instruction jump_over_else = {.opcode = OP_JUMP};
    uint32_t jump_over_else_idx = bytecode_emit(comp->program, jump_over_else);
    
    // Patch jump_to_else to point here (start of else branch)
    uint32_t else_start = comp->program->instruction_count;
    bytecode_patch_jump(comp->program, jump_to_else_idx, else_start);
    
    // Compile else branch
    compile_expr(comp, expr->data.if_expr.else_expr);
    
    // Patch jump_over_else to point here (after else)
    uint32_t after_else = comp->program->instruction_count;
    bytecode_patch_jump(comp->program, jump_over_else_idx, after_else);
}

void compile_expr(Compiler* comp, Expr* expr) {
    switch (expr->kind) {
        case EXPR_LIT_INT:
            compile_lit_int(comp, expr);
            break;
        case EXPR_LIT_FLOAT:
            compile_lit_float(comp, expr);
            break;
        case EXPR_LIT_STRING:
            compile_lit_string(comp, expr);
            break;
        case EXPR_LIT_BOOL:
            compile_lit_bool(comp, expr);
            break;
        case EXPR_LIT_UNIT:
            compile_lit_unit(comp);
            break;
        case EXPR_VAR:
            compile_var(comp, expr);
            break;
        case EXPR_BINARY:
            compile_binary(comp, expr);
            break;
        case EXPR_IF:
            compile_if(comp, expr);
            break;
        case EXPR_SEQ:
            compile_seq(comp, expr);
            break;
        case EXPR_LET:
            compile_let(comp, expr);
            break;
        case EXPR_APPLY:
            compile_apply(comp, expr);
            break;
        case EXPR_WHILE:
            compile_while(comp, expr);
            break;
        case EXPR_BREAK:
            // Jump to end of nearest enclosing loop
            if (!comp->loop_stack) {
                fprintf(stderr, "Error: break outside of loop\n");
                exit(1);
            }
            // Emit jump and add to pending list for later patching
            Instruction break_jump = {.opcode = OP_JUMP};
            uint32_t break_offset = bytecode_emit(comp->program, break_jump);
            // Add to pending breaks
            PendingJump* pending_break = malloc(sizeof(PendingJump));
            pending_break->instruction_offset = break_offset;
            pending_break->next = comp->loop_stack->pending_breaks;
            comp->loop_stack->pending_breaks = pending_break;
            break;
        case EXPR_CONTINUE:
            // Jump to start of nearest enclosing loop
            if (!comp->loop_stack) {
                fprintf(stderr, "Error: continue outside of loop\n");
                exit(1);
            }
            Instruction cont_jump = {.opcode = OP_JUMP, .operand.jump.target = comp->loop_stack->start_label};
            bytecode_emit(comp->program, cont_jump);
            break;
        case EXPR_RETURN:
            // Compile return value and emit OP_RETURN
            compile_expr(comp, expr->data.return_expr.value);
            Instruction ret = {.opcode = OP_RETURN};
            bytecode_emit(comp->program, ret);
            break;
        case EXPR_IO_WRITE:
            compile_io_write(comp, expr);
            break;
        case EXPR_IO_READ:
            compile_io_read(comp, expr);
            break;
        case EXPR_IO_OPEN:
            compile_io_open(comp, expr);
            break;
        case EXPR_IO_CLOSE:
            compile_io_close(comp, expr);
            break;
        default:
            fprintf(stderr, "Unsupported expression type: %d\n", expr->kind);
            exit(1);
    }
}

void compile_function(Compiler* comp, Definition* def) {
    uint32_t func_idx = 0;
    if (!compiler_find_function(comp, def->name, &func_idx, NULL)) {
        fprintf(stderr, "Function not declared: %s\n", def->name);
        exit(1);
    }

    comp->current_function = func_idx;
    comp->locals = NULL;
    comp->local_count = 0;
    comp->max_local_count = 0;

    ParamList* param = def->data.func.params;
    uint32_t param_count = 0;
    while (param) {
        TypeKind param_type = type_to_typekind(param->param->type);
        compiler_add_local(comp, param->param->name, param_type);
        param_count++;
        param = param->next;
    }

    bytecode_set_function_start(comp->program, func_idx, comp->program->instruction_count);

    compile_expr(comp, def->data.func.body);

    // Patch all pending jumps with actual label positions
    PendingJump* jump = comp->pending_jumps;
    while (jump) {
        // Find target label
        LabelInfo* label = comp->labels;
        bool found = false;
        while (label) {
            if (strcmp(label->name, jump->target_label) == 0) {
                // Patch the jump instruction
                comp->program->instructions[jump->instruction_offset].operand.jump.target = label->position;
                found = true;
                break;
            }
            label = label->next;
        }
        
        if (!found) {
            fprintf(stderr, "Error: Undefined label '%s' in function '%s'\n", jump->target_label, def->name);
            exit(1);
        }
        
        PendingJump* next = jump->next;
        free(jump->target_label);
        free(jump);
        jump = next;
    }
    
    // Clear labels for next function
    LabelInfo* label = comp->labels;
    while (label) {
        LabelInfo* next = label->next;
        free(label->name);
        free(label);
        label = next;
    }
    comp->labels = NULL;
    comp->pending_jumps = NULL;

    Instruction ret = {.opcode = OP_RETURN};
    bytecode_emit(comp->program, ret);

    bytecode_set_function_locals(comp->program, func_idx, comp->max_local_count, param_count);
}

// Compile an imported module and add its exports to the function table
static void compile_imported_module(Compiler* comp, const char* module_name) {
    // Check if already loaded
    LoadedModule* loaded = module_cache_get(comp->module_cache, module_name);
    if (loaded && loaded->parsed_module) {
        return;  // Already compiled
    }
    
    // Check for circular import
    if (loaded && loaded->is_compiling) {
        fprintf(stderr, "Error: Circular import detected for module '%s'\n", module_name);
        fprintf(stderr, "Module is currently being compiled and imports itself (directly or indirectly)\n");
        exit(1);
    }
    
    // Load module (finds .aisl file in search paths)
    if (!loaded) {
        loaded = module_load(comp->module_cache, module_name);
        if (!loaded) {
            fprintf(stderr, "Error: Cannot load module '%s'\n", module_name);
            exit(1);
        }
    }
    
    // Mark as compiling (circular import detection)
    loaded->is_compiling = true;
    
    // Read and parse the module file
    FILE* f = fopen(loaded->module_path, "r");
    if (!f) {
        fprintf(stderr, "Error: Cannot open %s\n", loaded->module_path);
        exit(1);
    }
    
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    char* source = malloc(fsize + 1);
    fread(source, 1, fsize, f);
    source[fsize] = '\0';
    fclose(f);
    
    // Parse module
    Lexer lexer;
    lexer_init(&lexer, source);
    
    Parser parser;
    parser_init(&parser, &lexer);
    
    Module* imported_module = parser_parse_module(&parser);
    
    if (parser.has_error) {
        fprintf(stderr, "Error parsing module %s: %s\n", module_name, parser.error_msg);
        free(source);
        exit(1);
    }
    
    // Store parsed module and source (DON'T FREE - AST points into source!)
    loaded->parsed_module = imported_module;
    loaded->source = source;  // Keep source alive for AST pointers
    
    // Recursively compile its imports first
    for (int i = 0; i < imported_module->import_count; i++) {
        Import* imp = imported_module->imports[i];
        compile_imported_module(comp, imp->module_name);
    }
    
    // Compile the imported module's functions
    // First pass: declare all functions
    DefList* current = imported_module->definitions;
    while (current) {
        if (current->def->kind == DEF_FUNCTION) {
            uint32_t param_count = 0;
            ParamList* param = current->def->data.func.params;
            while (param) {
                param_count++;
                param = param->next;
            }
            uint32_t idx = bytecode_declare_function(comp->program, current->def->name, 0, param_count);
            compiler_add_function(comp, current->def->name, idx, param_count);
        }
        current = current->next;
    }
    
    // Second pass: compile function bodies
    current = imported_module->definitions;
    while (current) {
        if (current->def->kind == DEF_FUNCTION) {
            compile_function(comp, current->def);
        }
        current = current->next;
    }
    
    // Mark as done compiling
    loaded->is_compiling = false;
    
    // Note: Don't free source - it's stored in loaded->source for AST pointers
}

void compile_module(Compiler* comp, Module* module) {
    comp->module = module;  // Store module for import checking
    
    // First: compile all imported modules
    for (int i = 0; i < module->import_count; i++) {
        Import* imp = module->imports[i];
        compile_imported_module(comp, imp->module_name);
    }
    
    // Then: compile this module
    // Check if module has test-spec but no main function
    bool has_test_spec = false;
    bool has_main = false;
    
    DefList* current = module->definitions;
    while (current) {
        if (current->def->kind == DEF_TEST_SPEC) {
            has_test_spec = true;
        }
        if (current->def->kind == DEF_FUNCTION && 
            strcmp(current->def->name, "main") == 0) {
            has_main = true;
        }
        current = current->next;
    }
    
    
    // Declare all user-defined functions FIRST (so we can reference them later)
    current = module->definitions;
    while (current) {
        if (current->def->kind == DEF_FUNCTION) {
            uint32_t param_count = 0;
            ParamList* param = current->def->data.func.params;
            while (param) {
                param_count++;
                param = param->next;
            }
            uint32_t idx = bytecode_declare_function(comp->program, current->def->name, 0, param_count);
            compiler_add_function(comp, current->def->name, idx, param_count);
        }
        current = current->next;
    }
    
    // If module has test-spec but no main, generate a test execution main
    // This generates bytecode that calls each test function and compares results
    // NOTE: This must happen AFTER function declarations so we can find target functions
    if (has_test_spec && !has_main) {
        // Declare main function
        uint32_t main_idx = bytecode_declare_function(comp->program, "main", 0, 0);
        compiler_add_function(comp, "main", main_idx, 0);
        
        // Set function start before emitting instructions
        bytecode_set_function_start(comp->program, main_idx, comp->program->instruction_count);
        
        // Collect all test-specs from the module
        TestSpec** specs = NULL;
        uint32_t spec_count = 0;
        DefList* def_iter = module->definitions;
        while (def_iter) {
            if (def_iter->def->kind == DEF_TEST_SPEC) {
                spec_count++;
                specs = realloc(specs, sizeof(TestSpec*) * spec_count);
                specs[spec_count - 1] = (TestSpec*)def_iter->def->data.test.test_spec;
            }
            def_iter = def_iter->next;
        }
        
        // For each test spec, generate bytecode to execute tests
        for (uint32_t si = 0; si < spec_count; si++) {
            TestSpec* spec = specs[si];
            
            // Find the target function to test
            FunctionInfo* target_func = NULL;
            FunctionInfo* func_iter = comp->functions;
            while (func_iter) {
                if (strcmp(func_iter->name, spec->target_function) == 0) {
                    target_func = func_iter;
                    break;
                }
                func_iter = func_iter->next;
            }
            
            if (!target_func) continue;  // Skip if function not found
            
            // Process each test case
            TestCaseList* tc_list = spec->data.test_cases;
            while (tc_list) {
                TestCase* tc = tc_list->test_case;
                
                // Print test name
                uint32_t desc_idx = bytecode_add_string(comp->program, tc->description);
                Instruction push_desc = {.opcode = OP_PUSH_STRING, .operand.uint_val = desc_idx};
                bytecode_emit(comp->program, push_desc);
                Instruction print_desc = {.opcode = OP_PRINT_STR};
                bytecode_emit(comp->program, print_desc);
                
                // Push input arguments onto stack
                ExprList* arg_list = tc->input_args;
                while (arg_list) {
                    Expr* arg = arg_list->expr;
                    
                    switch (arg->kind) {
                        case EXPR_LIT_INT: {
                            Instruction push_arg = {.opcode = OP_PUSH_INT, .operand.int_val = arg->data.int_val};
                            bytecode_emit(comp->program, push_arg);
                            break;
                        }
                        case EXPR_LIT_FLOAT: {
                            Instruction push_arg = {.opcode = OP_PUSH_FLOAT, .operand.float_val = arg->data.float_val};
                            bytecode_emit(comp->program, push_arg);
                            break;
                        }
                        case EXPR_LIT_STRING: {
                            uint32_t str_idx = bytecode_add_string(comp->program, arg->data.string_val);
                            Instruction push_arg = {.opcode = OP_PUSH_STRING, .operand.uint_val = str_idx};
                            bytecode_emit(comp->program, push_arg);
                            break;
                        }
                        case EXPR_LIT_BOOL: {
                            Instruction push_arg = {.opcode = OP_PUSH_BOOL, .operand.bool_val = arg->data.bool_val};
                            bytecode_emit(comp->program, push_arg);
                            break;
                        }
                        default:
                            break;
                    }
                    
                    arg_list = arg_list->next;
                }
                
                // Call the test function
                Instruction call_func = {
                    .opcode = OP_CALL,
                    .operand.call = {
                        .func_idx = target_func->index,
                        .arg_count = target_func->param_count
                    }
                };
                bytecode_emit(comp->program, call_func);
                
                // Duplicate result for error message (will be printed if test fails)
                Instruction dup_result = {.opcode = OP_DUP};
                bytecode_emit(comp->program, dup_result);
                // Stack: result, result
                
                // Compare result with expected value
                // Handle different expected value types
                if (tc->expected->kind == EXPR_LIT_STRING) {
                    // For string expected values (e.g. decimal results like "15")
                    // Convert result to string first
                    Instruction to_str = {.opcode = OP_STR_FROM_DECIMAL};
                    bytecode_emit(comp->program, to_str);
                    // Stack: result_str, result_original
                    
                    // Push expected value
                    uint32_t exp_idx = bytecode_add_string(comp->program, tc->expected->data.string_val);
                    Instruction push_exp = {.opcode = OP_PUSH_STRING, .operand.uint_val = exp_idx};
                    bytecode_emit(comp->program, push_exp);
                    // Stack: expected_str, result_str, result_original
                    
                    // Compare strings
                    Instruction cmp = {.opcode = OP_EQ_STR};
                    bytecode_emit(comp->program, cmp);
                    // Stack: bool, result_original
                } else if (tc->expected->kind == EXPR_LIT_BOOL) {
                    // For boolean expected values
                    // Result is already bool, just compare directly
                    Instruction push_exp_bool = {.opcode = OP_PUSH_BOOL, .operand.bool_val = tc->expected->data.bool_val};
                    bytecode_emit(comp->program, push_exp_bool);
                    // Stack: expected_bool, result_bool, result_original
                    
                    // Compare booleans
                    Instruction cmp = {.opcode = OP_EQ_BOOL};
                    bytecode_emit(comp->program, cmp);
                    // Stack: bool, result_original
                } else if (tc->expected->kind == EXPR_LIT_INT) {
                    // For integer expected values
                    Instruction push_exp_int = {.opcode = OP_PUSH_INT, .operand.int_val = tc->expected->data.int_val};
                    bytecode_emit(comp->program, push_exp_int);
                    // Stack: expected_int, result_int, result_original
                    
                    // Compare integers
                    Instruction cmp = {.opcode = OP_EQ_INT};
                    bytecode_emit(comp->program, cmp);
                    // Stack: bool, result_original
                } else if (tc->expected->kind == EXPR_LIT_FLOAT) {
                    // For float expected values
                    Instruction push_exp_float = {.opcode = OP_PUSH_FLOAT, .operand.float_val = tc->expected->data.float_val};
                    bytecode_emit(comp->program, push_exp_float);
                    // Stack: expected_float, result_float, result_original
                    
                    // Compare floats
                    Instruction cmp = {.opcode = OP_EQ_FLOAT};
                    bytecode_emit(comp->program, cmp);
                    // Stack: bool, result_original
                } else {
                    // Unsupported expected type - assume failure
                    // Push false to indicate failure
                    Instruction push_false = {.opcode = OP_PUSH_BOOL, .operand.bool_val = false};
                    bytecode_emit(comp->program, push_false);
                    // Pop the duplicate result value
                    Instruction pop_result = {.opcode = OP_POP};
                    bytecode_emit(comp->program, pop_result);
                }
                
                // At this point, stack: bool, result_original
                // Duplicate bool for conditional
                Instruction dup_bool = {.opcode = OP_DUP};
                bytecode_emit(comp->program, dup_bool);
                // Stack: bool, bool, result_original
                
                // Jump to fail if false (JUMP_IF_FALSE pops the bool it checks)
                // Pass path instructions: pop bool (1) + pop result (1) + push string (1) + print (1) + jump (1) = 5 instructions
                uint32_t fail_addr = comp->program->instruction_count + 6;  // +1 for the JUMP_IF_FALSE itself
                Instruction jmp_fail = {.opcode = OP_JUMP_IF_FALSE, .operand.uint_val = fail_addr};
                bytecode_emit(comp->program, jmp_fail);
                // Stack after jump (if true): bool, result_original
                
                // Pass case: pop both bool and result, then print " ✓\n"
                Instruction pop_bool_pass = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_bool_pass);
                // Stack: result_original
                Instruction pop_result_pass = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_result_pass);
                // Stack: empty
                
                uint32_t pass_msg_idx = bytecode_add_string(comp->program, " ✓\n");
                Instruction push_pass = {.opcode = OP_PUSH_STRING, .operand.uint_val = pass_msg_idx};
                bytecode_emit(comp->program, push_pass);
                Instruction print_pass = {.opcode = OP_PRINT_STR};
                bytecode_emit(comp->program, print_pass);
                
                // Jump over fail message
                uint32_t jump_over_fail_location = comp->program->instruction_count;
                Instruction jmp_end = {.opcode = OP_JUMP, .operand.uint_val = 0};  // Placeholder
                bytecode_emit(comp->program, jmp_end);
                
                // Fail case: print " ✗ - Expected: <exp>, Got: <actual>\n"
                // Stack when we get here: bool, result_original (because JUMP_IF_FALSE popped one bool)
                
                // Pop the remaining bool
                Instruction pop_bool_fail = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_bool_fail);
                // Stack: result_original
                
                // Print failure marker
                uint32_t fail_msg_idx = bytecode_add_string(comp->program, " ✗ - Expected: ");
                Instruction push_fail = {.opcode = OP_PUSH_STRING, .operand.uint_val = fail_msg_idx};
                bytecode_emit(comp->program, push_fail);
                Instruction print_fail = {.opcode = OP_PRINT_STR};
                bytecode_emit(comp->program, print_fail);
                // Pop the UNIT value left by print
                Instruction pop_unit_fail = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_unit_fail);
                
                // Print expected value as string
                char expected_str[256];
                if (tc->expected->kind == EXPR_LIT_INT) {
                    snprintf(expected_str, sizeof(expected_str), "%lld", tc->expected->data.int_val);
                } else if (tc->expected->kind == EXPR_LIT_BOOL) {
                    snprintf(expected_str, sizeof(expected_str), "%s", tc->expected->data.bool_val ? "true" : "false");
                } else if (tc->expected->kind == EXPR_LIT_FLOAT) {
                    snprintf(expected_str, sizeof(expected_str), "%g", tc->expected->data.float_val);
                } else if (tc->expected->kind == EXPR_LIT_STRING) {
                    snprintf(expected_str, sizeof(expected_str), "%s", tc->expected->data.string_val);
                } else {
                    snprintf(expected_str, sizeof(expected_str), "(unknown)");
                }
                uint32_t expected_str_idx = bytecode_add_string(comp->program, expected_str);
                Instruction push_expected = {.opcode = OP_PUSH_STRING, .operand.uint_val = expected_str_idx};
                bytecode_emit(comp->program, push_expected);
                Instruction print_expected = {.opcode = OP_PRINT_STR};
                bytecode_emit(comp->program, print_expected);
                // Pop the UNIT value left by print
                Instruction pop_unit1 = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_unit1);
                
                // Print ", Got: "
                uint32_t got_msg_idx = bytecode_add_string(comp->program, ", Got: ");
                Instruction push_got = {.opcode = OP_PUSH_STRING, .operand.uint_val = got_msg_idx};
                bytecode_emit(comp->program, push_got);
                Instruction print_got = {.opcode = OP_PRINT_STR};
                bytecode_emit(comp->program, print_got);
                // Pop the UNIT value left by print
                Instruction pop_unit2 = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_unit2);
                
                // Now stack has just: result_original
                // Print actual value
                Instruction print_actual = {.opcode = OP_PRINT_INT};
                if (tc->expected->kind == EXPR_LIT_INT) {
                    print_actual.opcode = OP_PRINT_INT;
                } else if (tc->expected->kind == EXPR_LIT_BOOL) {
                    print_actual.opcode = OP_PRINT_BOOL;
                } else if (tc->expected->kind == EXPR_LIT_FLOAT) {
                    print_actual.opcode = OP_PRINT_FLOAT;
                } else if (tc->expected->kind == EXPR_LIT_STRING) {
                    // String expected means this is a decimal test
                    // Convert decimal to string first
                    Instruction to_str = {.opcode = OP_STR_FROM_DECIMAL};
                    bytecode_emit(comp->program, to_str);
                    print_actual.opcode = OP_PRINT_STR;
                }
                bytecode_emit(comp->program, print_actual);
                // Pop the UNIT value left by print
                Instruction pop_unit3 = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_unit3);
                
                // Print newline
                uint32_t newline_idx = bytecode_add_string(comp->program, "\n");
                Instruction push_newline = {.opcode = OP_PUSH_STRING, .operand.uint_val = newline_idx};
                bytecode_emit(comp->program, push_newline);
                Instruction print_newline = {.opcode = OP_PRINT_STR};
                bytecode_emit(comp->program, print_newline);
                
                // Pop the UNIT value left by print
                Instruction pop_unit4 = {.opcode = OP_POP};
                bytecode_emit(comp->program, pop_unit4);
                
                // Update the jump-over-fail instruction with correct address
                uint32_t after_fail = comp->program->instruction_count;
                comp->program->instructions[jump_over_fail_location].operand.uint_val = after_fail;
                
                tc_list = tc_list->next;
            }
        }
        
        // Return 0 (success)
        Instruction push_zero = {.opcode = OP_PUSH_INT, .operand.int_val = 0};
        Instruction ret = {.opcode = OP_RETURN};
        bytecode_emit(comp->program, push_zero);
        bytecode_emit(comp->program, ret);
        
        free(specs);
    }

    current = module->definitions;
    while (current) {
        if (current->def->kind == DEF_FUNCTION) {
            compile_function(comp, current->def);
        }
        current = current->next;
    }

    // Add halt at the end
    Instruction halt = {.opcode = OP_HALT};
    bytecode_emit(comp->program, halt);
}

int main(int argc, char** argv) {
    bool export_ast = false;
    const char* input_file = NULL;
    const char* output_file = NULL;
    
    // Parse arguments
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--ast-export") == 0) {
            export_ast = true;
        } else if (!input_file) {
            input_file = argv[i];
        } else if (!output_file) {
            output_file = argv[i];
        }
    }
    
    if (!input_file || !output_file) {
        fprintf(stderr, "Usage: %s [--ast-export] <input.aisl> <output.aislc>\n", argv[0]);
        fprintf(stderr, "  --ast-export    Export AST to <output>.ast file\n");
        return 1;
    }

    // Read source
    FILE* f = fopen(input_file, "r");
    if (!f) {
        fprintf(stderr, "Error: Cannot open %s\n", input_file);
        return 1;
    }

    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);

    char* source = malloc(fsize + 1);
    fread(source, 1, fsize, f);
    source[fsize] = '\0';
    fclose(f);

    // Parse
    Lexer lexer;
    lexer_init(&lexer, source);

    Parser parser;
    parser_init(&parser, &lexer);

    Module* module = parser_parse_module(&parser);

    if (parser.has_error) {
        // Check for machine-readable error format
        const char* error_format = getenv("AISL_ERROR_FORMAT");
        if (error_format && strcmp(error_format, "machine") == 0) {
            // Machine-readable format: ERROR:CODE:LINE:COL:MESSAGE
            // Extract just the message without "Parse error at line X: " prefix
            const char* msg = parser.error_msg;
            const char* colon = strstr(msg, ": ");
            if (colon) msg = colon + 2;
            
            fprintf(stderr, "ERROR:%s:%d:0:%s\n", 
                    parser.error_code, parser.current.line, msg);
        } else {
            // Human-readable format (default)
            fprintf(stderr, "Parse error: %s\n", parser.error_msg);
        }
        free(source);
        return 1;
    }
    
    // Desugar Agent constructs (while, loop, break, continue) to Core (label, goto, ifnot, set, call, ret)
    module = desugar_module(module);
    
    // Export AST if requested
    if (export_ast) {
        char ast_file[512];
        snprintf(ast_file, sizeof(ast_file), "%s.ast", output_file);
        FILE* ast_out = fopen(ast_file, "w");
        if (ast_out) {
            ast_export_module(ast_out, module);
            fclose(ast_out);
            printf("Exported AST -> %s\n", ast_file);
        } else {
            fprintf(stderr, "Warning: Could not open %s for AST export\n", ast_file);
        }
    }

    // Compile to bytecode
    Compiler compiler;
    compiler_init(&compiler);
    compile_module(&compiler, module);

    // Save bytecode
    bytecode_save(compiler.program, output_file);

    printf("Compiled %s -> %s\n", input_file, output_file);
    printf("Functions: %d\n", compiler.program->function_count);
    printf("Instructions: %d\n", compiler.program->instruction_count);

    free(source);
    free_module(module);
    bytecode_program_free(compiler.program);

    return 0;
}
