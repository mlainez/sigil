#define _POSIX_C_SOURCE 200809L
#include "bytecode.h"
#include "parser.h"
#include "lexer.h"
#include "ast_export.h"
#include "desugar.h"
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
    // For example: "add" + TYPE_I32 -> "op_add_i32"
    
    // Use multiple buffers to avoid overwrites during nested compilation
    static char buffers[8][64];
    static int buffer_index = 0;
    char* buffer = buffers[buffer_index];
    buffer_index = (buffer_index + 1) % 8;
    
    // String operations (handle these first before type_suffix check)
    if (strcmp(short_name, "concat") == 0) return "string_concat";
    if (strcmp(short_name, "slice") == 0) return "string_slice";
    if (strcmp(short_name, "from_i32") == 0) return "string_from_i32";
    if (strcmp(short_name, "from_i64") == 0) return "string_from_i64";
    if (strcmp(short_name, "from_f32") == 0) return "string_from_f32";
    if (strcmp(short_name, "from_f64") == 0) return "string_from_f64";
    if (strcmp(short_name, "from_bool") == 0) return "string_from_bool";
    
    // Length operation - could be array or string, need context
    if (strcmp(short_name, "len") == 0) {
        if (type == TYPE_STRING) return "string_length";
        return "array_length";
    }
    
    const char* type_suffix = "";
    
    switch (type) {
        case TYPE_I32: type_suffix = "_i32"; break;
        case TYPE_I64: type_suffix = "_i64"; break;
        case TYPE_F32: type_suffix = "_f32"; break;
        case TYPE_F64: type_suffix = "_f64"; break;
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
        strcmp(short_name, "max") == 0) {
        snprintf(buffer, 64, "math_%s%s", short_name, type_suffix);
        return buffer;
    }
    
    // I/O operations - dispatch on argument type
    if (strcmp(short_name, "print") == 0) {
        switch (type) {
            case TYPE_I32: return "io_print_i32";
            case TYPE_I64: return "io_print_i64";
            case TYPE_F32: return "io_print_f32";
            case TYPE_F64: return "io_print_f64";
            case TYPE_BOOL: return "io_print_bool";
            case TYPE_STRING: return "io_print_str";
            case TYPE_ARRAY: return "io_print_array";
            case TYPE_MAP: return "io_print_map";
            default: return "io_print_i32";
        }
    }
    
    // Array operations (type-agnostic in VM, but keep existing names)
    if (strcmp(short_name, "push") == 0) return "array_push";
    if (strcmp(short_name, "get") == 0) return "array_get";
    if (strcmp(short_name, "set") == 0) return "array_set";
    
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
        .opcode = OP_PUSH_F64,
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

    // Type-directed dispatch for polymorphic operations
    // Check if this is a short polymorphic operation (add, sub, mul, etc.)
    if (strcmp(name, "add") == 0 || strcmp(name, "sub") == 0 || 
        strcmp(name, "mul") == 0 || strcmp(name, "div") == 0 ||
        strcmp(name, "mod") == 0 || strcmp(name, "neg") == 0 ||
        strcmp(name, "eq") == 0 || strcmp(name, "ne") == 0 ||
        strcmp(name, "lt") == 0 || strcmp(name, "gt") == 0 ||
        strcmp(name, "le") == 0 || strcmp(name, "ge") == 0 ||
        strcmp(name, "abs") == 0 || strcmp(name, "min") == 0 ||
        strcmp(name, "max") == 0 ||
        strcmp(name, "print") == 0 || strcmp(name, "len") == 0 ||
        strcmp(name, "push") == 0 || strcmp(name, "get") == 0 ||
        strcmp(name, "set") == 0 || strcmp(name, "concat") == 0 ||
        strcmp(name, "slice") == 0 || strcmp(name, "from_i32") == 0 ||
        strcmp(name, "from_i64") == 0 || strcmp(name, "from_f32") == 0 ||
        strcmp(name, "from_f64") == 0 || strcmp(name, "from_bool") == 0) {
        
        // Get type from first argument
        if (!expr->data.apply.args) {
            fprintf(stderr, "Operation '%s' requires at least one argument\n", name);
            exit(1);
        }
        
        // Check if first argument is a variable reference
        Expr* first_arg = expr->data.apply.args->expr;
        TypeKind arg_type = TYPE_I32;  // Default to i32 if type can't be determined
        
        if (first_arg->kind == EXPR_VAR) {
            // Look up variable type
            uint32_t dummy_idx;
            if (!compiler_find_local(comp, first_arg->data.var.name, &dummy_idx, &arg_type)) {
                fprintf(stderr, "Undefined variable in operation: %s\n", first_arg->data.var.name);
                exit(1);
            }
        } else if (first_arg->kind == EXPR_LIT_INT) {
            // Integer literal defaults to i32
            arg_type = TYPE_I32;
        } else if (first_arg->kind == EXPR_LIT_FLOAT) {
            // Float literal defaults to f64
            arg_type = TYPE_F64;
        } else if (first_arg->kind == EXPR_LIT_STRING) {
            // String literal
            arg_type = TYPE_STRING;
        } else if (first_arg->type) {
            // Use type from expression
            arg_type = type_to_typekind(first_arg->type);
            // If we got TYPE_UNIT (unknown type from nested expr), default to TYPE_I32
            // But preserve TYPE_STRING and other known types
            if (arg_type == TYPE_UNIT) {
                arg_type = TYPE_I32;
            }
        }
        // Otherwise use default TYPE_I32
        
        // Map to typed operation
        const char* typed_name = get_typed_operation(name, arg_type);
        
        // Replace name with typed version and continue with normal compilation
        name = typed_name;
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
    if (strcmp(name, "if_i32") == 0 || strcmp(name, "if_i64") == 0 || 
        strcmp(name, "if_f32") == 0 || strcmp(name, "if_f64") == 0 ||
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

    // V3.0 Builtins
    if (strcmp(name, "print") == 0) {
        // print(str) -> IO_WRITE(1, str)
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "print expects exactly 1 argument\n");
            exit(1);
        }
        // Push handle (stdout = 1)
        Instruction push_handle = {.opcode = OP_PUSH_INT, .operand.int_val = 1};
        bytecode_emit(comp->program, push_handle);

        // Compile the string argument
        compile_expr(comp, expr->data.apply.args->expr);

        // Perform IO_WRITE
        Instruction io_write = {.opcode = OP_IO_WRITE};
        bytecode_emit(comp->program, io_write);
        return;
    }

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

    // V4.0 Typed print builtins
    if (strcmp(name, "io_print_i32") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_i32 expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    
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
    
    if (strcmp(name, "io_print_f32") == 0) {
        if (expr->data.apply.args == NULL || expr->data.apply.args->next != NULL) {
            fprintf(stderr, "io_print_f32 expects exactly 1 argument\n");
            exit(1);
        }
        compile_expr(comp, expr->data.apply.args->expr);
        Instruction inst = {.opcode = OP_PRINT_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    
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

    // V4.0 Typed arithmetic operations - i32
    if (strcmp(name, "op_add_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_add_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ADD_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_sub_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_sub_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SUB_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_mul_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_mul_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MUL_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_div_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_div_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIV_I32};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed arithmetic operations - i64
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

    // V4.0 Typed arithmetic operations - f32
    if (strcmp(name, "op_add_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_add_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_ADD_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_sub_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_sub_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SUB_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_mul_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_mul_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MUL_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_div_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_div_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_DIV_F32};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed arithmetic operations - f64
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

    // V4.0 Typed comparison operations - i32
    if (strcmp(name, "op_eq_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_eq_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ne_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ne_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NE_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_lt_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_lt_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LT_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_gt_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_gt_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GT_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_le_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_le_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LE_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ge_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ge_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GE_I32};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed comparison operations - i64
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

    // V4.0 Typed comparison operations - f32
    if (strcmp(name, "op_eq_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_eq_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ne_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ne_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_NE_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_lt_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_lt_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LT_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_gt_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_gt_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GT_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_le_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_le_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_LE_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "op_ge_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "op_ge_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_GE_F32};
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.0 Typed comparison operations - f64
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

    // V4.0 Type conversion operations
    if (strcmp(name, "cast_i32_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i32_i64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I32_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_i64_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i64_i32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I64_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_i32_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i32_f32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I32_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_i32_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i32_f64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I32_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_i64_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i64_f32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I64_F32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_i64_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_i64_f64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_I64_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_f32_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_f32_i32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_F32_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_f32_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_f32_i64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_F32_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_f64_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_f64_i32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_F64_I32};
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
    if (strcmp(name, "cast_f32_f64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_f32_f64 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_F32_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "cast_f64_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "cast_f64_f32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_CAST_F64_F32};
        bytecode_emit(comp->program, inst);
        return;
    }

    // Math functions
    if (strcmp(name, "math_sqrt") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "math_sqrt expects 1 argument (f64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_SQRT_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_pow") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_pow expects 2 arguments (base f64, exp f64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_POW_F64};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "math_abs_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "math_abs_i32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_ABS_I32};
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
    if (strcmp(name, "math_abs_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "math_abs_f32 expects 1 argument\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_ABS_F32};
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
    if (strcmp(name, "math_min_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_min_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MIN_I32};
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
    if (strcmp(name, "math_min_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_min_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MIN_F32};
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
    if (strcmp(name, "math_max_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_max_i32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MAX_I32};
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
    if (strcmp(name, "math_max_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "math_max_f32 expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_MATH_MAX_F32};
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
            fprintf(stderr, "string_slice expects 3 arguments (str, start, end)\n");
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
    
    if (strcmp(name, "string_eq") == 0) {
        // String equality using generic comparison
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_eq expects 2 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_EQ_INT};  // Use generic equality
        bytecode_emit(comp->program, inst);
        return;
    }

    // V4.1 String conversion operations
    if (strcmp(name, "string_from_i32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_from_i32 expects 1 argument (i32)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_FROM_I32};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_from_i64") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_from_i64 expects 1 argument (i64)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_FROM_I64};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_from_f32") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_from_f32 expects 1 argument (f32)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_FROM_F32};
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

    // V4.2 Advanced String operations
    if (strcmp(name, "string_split") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_split expects 2 arguments (str, delimiter)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_SPLIT};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_trim") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_trim expects 1 argument (str)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_TRIM};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_contains") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_contains expects 2 arguments (str, substring)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_CONTAINS};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "string_replace") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "string_replace expects 3 arguments (string, old, new)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_REPLACE};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "string_starts_with") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_starts_with expects 2 arguments (string, prefix)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_STARTS_WITH};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "string_ends_with") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "string_ends_with expects 2 arguments (string, suffix)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_ENDS_WITH};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "string_to_upper") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_to_upper expects 1 argument (string)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_TO_UPPER};
        bytecode_emit(comp->program, inst);
        return;
    }

    if (strcmp(name, "string_to_lower") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "string_to_lower expects 1 argument (string)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_STR_TO_LOWER};
        bytecode_emit(comp->program, inst);
        return;
    }

    
    if (strcmp(name, "array_new") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "array_new expects 1 argument (capacity)\n");
            exit(1);
        }
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
    
    // JSON operations (v4.4)
    if (strcmp(name, "json_parse") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "json_parse expects 1 argument (string)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_PARSE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_stringify") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "json_stringify expects 1 argument (json)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_STRINGIFY};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_new_object") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "json_new_object expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_NEW_OBJECT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_new_array") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 0) {
            fprintf(stderr, "json_new_array expects 0 arguments\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_NEW_ARRAY};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_get") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "json_get expects 2 arguments (json, key)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_GET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_set") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "json_set expects 3 arguments (json, key, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_SET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_push") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "json_push expects 2 arguments (json, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_PUSH};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_length") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "json_length expects 1 argument (json)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_LENGTH};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "json_type") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "json_type expects 1 argument (json)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_JSON_TYPE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    if (strcmp(name, "http_get") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "http_get expects 1 argument (url string)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_HTTP_GET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "http_get_status") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "http_get_status expects 1 argument (response)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_HTTP_GET_STATUS};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "http_get_body") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "http_get_body expects 1 argument (response)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_HTTP_GET_BODY};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "http_post") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "http_post expects 2 arguments (url, body)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_HTTP_POST};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "http_put") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "http_put expects 2 arguments (url, body)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_HTTP_PUT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "http_delete") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "http_delete expects 1 argument (url)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_HTTP_DELETE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
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
    
    // Result type operations
    if (strcmp(name, "result_ok") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "result_ok expects 1 argument (value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_OK};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "result_err") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "result_err expects 2 arguments (error_code, error_message)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_ERR};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "is_ok") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "is_ok expects 1 argument (result)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_IS_OK};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "is_err") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "is_err expects 1 argument (result)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_IS_ERR};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "unwrap") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "unwrap expects 1 argument (result)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_UNWRAP};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "unwrap_or") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "unwrap_or expects 2 arguments (result, default_value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_UNWRAP_OR};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "error_code") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "error_code expects 1 argument (result)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_ERROR_CODE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "error_message") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "error_message expects 1 argument (result)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_RESULT_ERROR_MSG};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // File operations with result type
    if (strcmp(name, "file_read_result") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "file_read_result expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_READ_RESULT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_write_result") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "file_write_result expects 2 arguments (path, content)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_WRITE_RESULT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "file_append_result") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "file_append_result expects 2 arguments (path, content)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_FILE_APPEND_RESULT};
        bytecode_emit(comp->program, inst);
        return;
    }
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
    
    if (strcmp(name, "base64_encode") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "base64_encode expects 1 argument (input)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_BASE64_ENCODE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "base64_decode") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "base64_decode expects 1 argument (input)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_BASE64_DECODE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
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
    
    // ============================================
    // SQLITE DATABASE OPERATIONS
    // ============================================
    
    if (strcmp(name, "sqlite_open") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "sqlite_open expects 1 argument (path)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_OPEN};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_close") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "sqlite_close expects 1 argument (db)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_CLOSE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_exec") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "sqlite_exec expects 2 arguments (db, sql)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_EXEC};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_query") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "sqlite_query expects 2 arguments (db, sql)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_QUERY};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_prepare") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "sqlite_prepare expects 2 arguments (db, sql)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_PREPARE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_bind") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 3) {
            fprintf(stderr, "sqlite_bind expects 3 arguments (stmt, index, value)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_BIND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_step") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "sqlite_step expects 1 argument (stmt)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_STEP};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_column") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "sqlite_column expects 2 arguments (stmt, index)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_COLUMN};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_reset") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "sqlite_reset expects 1 argument (stmt)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_RESET};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "sqlite_finalize") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "sqlite_finalize expects 1 argument (stmt)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_SQLITE_FINALIZE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // ============================================
    // WEBSOCKET OPERATIONS
    // ============================================
    
    if (strcmp(name, "ws_connect") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ws_connect expects 1 argument (url)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_WS_CONNECT};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ws_send") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 2) {
            fprintf(stderr, "ws_send expects 2 arguments (ws, message)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_WS_SEND};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ws_receive") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ws_receive expects 1 argument (ws)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_WS_RECEIVE};
        bytecode_emit(comp->program, inst);
        return;
    }
    if (strcmp(name, "ws_close") == 0) {
        if (compile_args(comp, expr->data.apply.args) != 1) {
            fprintf(stderr, "ws_close expects 1 argument (ws)\n");
            exit(1);
        }
        Instruction inst = {.opcode = OP_WS_CLOSE};
        bytecode_emit(comp->program, inst);
        return;
    }
    
    // ============================================
    // PROCESS MANAGEMENT OPERATIONS
    // ============================================
    
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
    
    // ============================================
    // NETWORK SOCKET OPERATIONS
    // ============================================
    
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
    
    // ============================================
    // GARBAGE COLLECTION OPERATIONS
    // ============================================
    
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
    while (param) {
        TypeKind param_type = type_to_typekind(param->param->type);
        compiler_add_local(comp, param->param->name, param_type);
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

    bytecode_set_function_locals(comp->program, func_idx, comp->max_local_count);
}

void compile_module(Compiler* comp, Module* module) {
    DefList* current = module->definitions;
    while (current) {
        if (current->def->kind == DEF_FUNCTION) {
            uint32_t param_count = 0;
            ParamList* param = current->def->data.func.params;
            while (param) {
                param_count++;
                param = param->next;
            }
            uint32_t idx = bytecode_declare_function(comp->program, current->def->name, 0);
            compiler_add_function(comp, current->def->name, idx, param_count);
        }
        current = current->next;
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
