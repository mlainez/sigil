#define _POSIX_C_SOURCE 200809L
#include "bytecode.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

typedef struct {
    const char* p;
} TextScanner;

static bool text_next_token(TextScanner* scanner, char* out, size_t out_size) {
    while (*scanner->p && isspace((unsigned char)*scanner->p)) {
        scanner->p++;
    }
    if (!*scanner->p) {
        return false;
    }
    if (*scanner->p == '"' || *scanner->p == '\'') {
        char quote = *scanner->p++;
        size_t i = 0;
        while (*scanner->p && *scanner->p != quote && i + 1 < out_size) {
            out[i++] = *scanner->p++;
        }
        out[i] = '\0';
        if (*scanner->p == quote) {
            scanner->p++;
        }
        return true;
    }
    size_t i = 0;
    while (*scanner->p && !isspace((unsigned char)*scanner->p) && i + 1 < out_size) {
        out[i++] = *scanner->p++;
    }
    out[i] = '\0';
    return true;
}

BytecodeProgram* bytecode_program_new() {
    BytecodeProgram* program = malloc(sizeof(BytecodeProgram));

    program->instruction_capacity = 1024;
    program->instructions = malloc(sizeof(Instruction) * program->instruction_capacity);
    program->instruction_count = 0;

    program->function_capacity = 64;
    program->functions = malloc(sizeof(Function) * program->function_capacity);
    program->function_count = 0;

    program->string_capacity = 256;
    program->string_constants = malloc(sizeof(char*) * program->string_capacity);
    program->string_count = 0;

    return program;
}

void bytecode_program_free(BytecodeProgram* program) {
    free(program->instructions);

    for (uint32_t i = 0; i < program->function_count; i++) {
        free(program->functions[i].name);
    }
    free(program->functions);

    for (uint32_t i = 0; i < program->string_count; i++) {
        free(program->string_constants[i]);
    }
    free(program->string_constants);

    free(program);
}

uint32_t bytecode_emit(BytecodeProgram* program, Instruction inst) {
    if (program->instruction_count >= program->instruction_capacity) {
        program->instruction_capacity *= 2;
        program->instructions = realloc(program->instructions,
                                       sizeof(Instruction) * program->instruction_capacity);
    }

    uint32_t offset = program->instruction_count;
    program->instructions[program->instruction_count++] = inst;
    return offset;
}

uint32_t bytecode_add_string(BytecodeProgram* program, const char* str) {
    if (program->string_count >= program->string_capacity) {
        program->string_capacity *= 2;
        program->string_constants = realloc(program->string_constants,
                                           sizeof(char*) * program->string_capacity);
    }

    uint32_t idx = program->string_count;
    program->string_constants[program->string_count++] = strdup(str);
    return idx;
}

uint32_t bytecode_declare_function(BytecodeProgram* program, const char* name, uint32_t local_count) {
    if (program->function_count >= program->function_capacity) {
        program->function_capacity *= 2;
        program->functions = realloc(program->functions,
                                    sizeof(Function) * program->function_capacity);
    }

    uint32_t idx = program->function_count;
    program->functions[idx].name = strdup(name);
    program->functions[idx].start_addr = 0;
    program->functions[idx].local_count = local_count;
    program->function_count++;

    return idx;
}

void bytecode_set_function_start(BytecodeProgram* program, uint32_t idx, uint32_t start_addr) {
    if (idx < program->function_count) {
        program->functions[idx].start_addr = start_addr;
    }
}

void bytecode_set_function_locals(BytecodeProgram* program, uint32_t idx, uint32_t local_count) {
    if (idx < program->function_count) {
        program->functions[idx].local_count = local_count;
    }
}

uint32_t bytecode_add_function(BytecodeProgram* program, const char* name, uint32_t local_count) {
    uint32_t idx = bytecode_declare_function(program, name, local_count);
    program->functions[idx].start_addr = program->instruction_count;
    return idx;
}

void bytecode_patch_jump(BytecodeProgram* program, uint32_t offset, uint32_t target) {
    program->instructions[offset].operand.jump.target = target;
}

// ============================================
// SERIALIZATION
// ============================================

void bytecode_save(BytecodeProgram* program, const char* filename) {
    FILE* f = fopen(filename, "wb");
    if (!f) {
        fprintf(stderr, "Error: Cannot write to %s\n", filename);
        return;
    }

    // Write magic number
    uint32_t magic = 0x4149534C; // "AISL"
    fwrite(&magic, sizeof(uint32_t), 1, f);

    // Write instruction count and instructions
    fwrite(&program->instruction_count, sizeof(uint32_t), 1, f);
    fwrite(program->instructions, sizeof(Instruction), program->instruction_count, f);

    // Write string constants
    fwrite(&program->string_count, sizeof(uint32_t), 1, f);
    for (uint32_t i = 0; i < program->string_count; i++) {
        uint32_t len = strlen(program->string_constants[i]);
        fwrite(&len, sizeof(uint32_t), 1, f);
        fwrite(program->string_constants[i], 1, len, f);
    }

    // Write functions
    fwrite(&program->function_count, sizeof(uint32_t), 1, f);
    for (uint32_t i = 0; i < program->function_count; i++) {
        uint32_t len = strlen(program->functions[i].name);
        fwrite(&len, sizeof(uint32_t), 1, f);
        fwrite(program->functions[i].name, 1, len, f);
        fwrite(&program->functions[i].start_addr, sizeof(uint32_t), 1, f);
        fwrite(&program->functions[i].local_count, sizeof(uint32_t), 1, f);
    }

    fclose(f);
}

BytecodeProgram* bytecode_load(const char* filename) {
    FILE* f = fopen(filename, "rb");
    if (!f) {
        fprintf(stderr, "Error: Cannot read %s\n", filename);
        return NULL;
    }

    char header[10] = {0};
    size_t header_len = fread(header, 1, 9, f);
    if (header_len == 9 && memcmp(header, "AISLTEXT1", 9) == 0) {
        fseek(f, 0, SEEK_SET);
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (size <= 0) {
            fclose(f);
            return NULL;
        }

        char* buffer = malloc((size_t)size + 1);
        fread(buffer, 1, (size_t)size, f);
        buffer[size] = '\0';
        fclose(f);

        TextScanner scanner = {.p = buffer};

        char tok[256];
        if (!text_next_token(&scanner, tok, sizeof(tok)) || strcmp(tok, "AISLTEXT1") != 0) {
            free(buffer);
            return NULL;
        }

        if (!text_next_token(&scanner, tok, sizeof(tok)) || strcmp(tok, "strings") != 0) {
            free(buffer);
            return NULL;
        }

        if (!text_next_token(&scanner, tok, sizeof(tok))) {
            free(buffer);
            return NULL;
        }

        uint32_t string_count = (uint32_t)strtoul(tok, NULL, 10);

        BytecodeProgram* program = bytecode_program_new();
        program->string_count = 0;
        for (uint32_t i = 0; i < string_count; i++) {
            if (!text_next_token(&scanner, tok, sizeof(tok))) {
                free(buffer);
                bytecode_program_free(program);
                return NULL;
            }
            bytecode_add_string(program, tok);
        }

        if (!text_next_token(&scanner, tok, sizeof(tok)) || strcmp(tok, "functions") != 0) {
            free(buffer);
            bytecode_program_free(program);
            return NULL;
        }

        if (!text_next_token(&scanner, tok, sizeof(tok))) {
            free(buffer);
            bytecode_program_free(program);
            return NULL;
        }

        uint32_t function_count = (uint32_t)strtoul(tok, NULL, 10);
        for (uint32_t i = 0; i < function_count; i++) {
            char name[256];
            if (!text_next_token(&scanner, name, sizeof(name))) {
                free(buffer);
                bytecode_program_free(program);
                return NULL;
            }
            if (!text_next_token(&scanner, tok, sizeof(tok))) {
                free(buffer);
                bytecode_program_free(program);
                return NULL;
            }
            uint32_t start = (uint32_t)strtoul(tok, NULL, 10);
            if (!text_next_token(&scanner, tok, sizeof(tok))) {
                free(buffer);
                bytecode_program_free(program);
                return NULL;
            }
            uint32_t locals = (uint32_t)strtoul(tok, NULL, 10);

            uint32_t idx = bytecode_declare_function(program, name, locals);
            bytecode_set_function_start(program, idx, start);
        }

        if (!text_next_token(&scanner, tok, sizeof(tok)) || strcmp(tok, "instructions") != 0) {
            free(buffer);
            bytecode_program_free(program);
            return NULL;
        }

        if (!text_next_token(&scanner, tok, sizeof(tok))) {
            free(buffer);
            bytecode_program_free(program);
            return NULL;
        }

        uint32_t instr_count = (uint32_t)strtoul(tok, NULL, 10);
        for (uint32_t i = 0; i < instr_count; i++) {
            if (!text_next_token(&scanner, tok, sizeof(tok))) {
                free(buffer);
                bytecode_program_free(program);
                return NULL;
            }

            Instruction inst = {0};
            if (strcmp(tok, "PUSH_INT") == 0) {
                inst.opcode = OP_PUSH_INT;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.int_val = strtoll(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_STRING") == 0) {
                inst.opcode = OP_PUSH_STRING;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_BOOL") == 0) {
                inst.opcode = OP_PUSH_BOOL;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.bool_val = (strcmp(tok, "true") == 0) || (strcmp(tok, "1") == 0);
            } else if (strcmp(tok, "PUSH_UNIT") == 0) {
                inst.opcode = OP_PUSH_UNIT;
            } else if (strcmp(tok, "POP") == 0) {
                inst.opcode = OP_POP;
            } else if (strcmp(tok, "DUP") == 0) {
                inst.opcode = OP_DUP;
            } else if (strcmp(tok, "LOAD_LOCAL") == 0) {
                inst.opcode = OP_LOAD_LOCAL;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "STORE_LOCAL") == 0) {
                inst.opcode = OP_STORE_LOCAL;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "ADD_INT") == 0) {
                inst.opcode = OP_ADD_INT;
            } else if (strcmp(tok, "SUB_INT") == 0) {
                inst.opcode = OP_SUB_INT;
            } else if (strcmp(tok, "MUL_INT") == 0) {
                inst.opcode = OP_MUL_INT;
            } else if (strcmp(tok, "DIV_INT") == 0) {
                inst.opcode = OP_DIV_INT;
            } else if (strcmp(tok, "MOD_INT") == 0) {
                inst.opcode = OP_MOD_INT;
            } else if (strcmp(tok, "EQ_INT") == 0) {
                inst.opcode = OP_EQ_INT;
            } else if (strcmp(tok, "NEQ_INT") == 0) {
                inst.opcode = OP_NEQ_INT;
            } else if (strcmp(tok, "LT_INT") == 0) {
                inst.opcode = OP_LT_INT;
            } else if (strcmp(tok, "GT_INT") == 0) {
                inst.opcode = OP_GT_INT;
            } else if (strcmp(tok, "LTE_INT") == 0) {
                inst.opcode = OP_LTE_INT;
            } else if (strcmp(tok, "GTE_INT") == 0) {
                inst.opcode = OP_GTE_INT;
            } else if (strcmp(tok, "AND") == 0) {
                inst.opcode = OP_AND;
            } else if (strcmp(tok, "OR") == 0) {
                inst.opcode = OP_OR;
            } else if (strcmp(tok, "NOT") == 0) {
                inst.opcode = OP_NOT;
            } else if (strcmp(tok, "JUMP") == 0) {
                inst.opcode = OP_JUMP;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.jump.target = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "JUMP_IF_FALSE") == 0) {
                inst.opcode = OP_JUMP_IF_FALSE;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.jump.target = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "CALL") == 0) {
                inst.opcode = OP_CALL;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.call.func_idx = (uint32_t)strtoul(tok, NULL, 10);
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.call.arg_count = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "RETURN") == 0) {
                inst.opcode = OP_RETURN;
            } else if (strcmp(tok, "IO_WRITE") == 0) {
                inst.opcode = OP_IO_WRITE;
            } else if (strcmp(tok, "IO_READ") == 0) {
                inst.opcode = OP_IO_READ;
            } else if (strcmp(tok, "IO_OPEN") == 0) {
                inst.opcode = OP_IO_OPEN;
            } else if (strcmp(tok, "IO_CLOSE") == 0) {
                inst.opcode = OP_IO_CLOSE;
            } else if (strcmp(tok, "STR_LEN") == 0) {
                inst.opcode = OP_STR_LEN;
            } else if (strcmp(tok, "STR_CONCAT") == 0) {
                inst.opcode = OP_STR_CONCAT;
            } else if (strcmp(tok, "STR_SLICE") == 0) {
                inst.opcode = OP_STR_SLICE;
            } else if (strcmp(tok, "STR_GET") == 0) {
                inst.opcode = OP_STR_GET;
            } else if (strcmp(tok, "ARRAY_NEW") == 0) {
                inst.opcode = OP_ARRAY_NEW;
            } else if (strcmp(tok, "ARRAY_PUSH") == 0) {
                inst.opcode = OP_ARRAY_PUSH;
            } else if (strcmp(tok, "ARRAY_GET") == 0) {
                inst.opcode = OP_ARRAY_GET;
            } else if (strcmp(tok, "ARRAY_SET") == 0) {
                inst.opcode = OP_ARRAY_SET;
            } else if (strcmp(tok, "ARRAY_LEN") == 0) {
                inst.opcode = OP_ARRAY_LEN;
            } else if (strcmp(tok, "HALT") == 0) {
                inst.opcode = OP_HALT;
            } else if (strcmp(tok, "PRINT_DEBUG") == 0) {
                inst.opcode = OP_PRINT_DEBUG;
            }
            // Typed push operations
            else if (strcmp(tok, "PUSH_I8") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.int_val = strtoll(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_I16") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.int_val = strtoll(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_I32") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.int_val = strtoll(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_I64") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.int_val = strtoll(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_U8") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_U16") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_U32") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_U64") == 0) {
                inst.opcode = OP_PUSH_I64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.uint_val = (uint32_t)strtoul(tok, NULL, 10);
            } else if (strcmp(tok, "PUSH_F32") == 0) {
                inst.opcode = OP_PUSH_F64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.float_val = strtod(tok, NULL);
            } else if (strcmp(tok, "PUSH_F64") == 0) {
                inst.opcode = OP_PUSH_F64;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.float_val = strtod(tok, NULL);
            }
            // Typed I32 arithmetic
            else if (strcmp(tok, "ADD_I32") == 0) {
                inst.opcode = OP_ADD_I64;
            } else if (strcmp(tok, "SUB_I32") == 0) {
                inst.opcode = OP_SUB_I64;
            } else if (strcmp(tok, "MUL_I32") == 0) {
                inst.opcode = OP_MUL_I64;
            } else if (strcmp(tok, "DIV_I32") == 0) {
                inst.opcode = OP_DIV_I64;
            } else if (strcmp(tok, "MOD_I32") == 0) {
                inst.opcode = OP_MOD_I64;
            } else if (strcmp(tok, "NEG_I32") == 0) {
                inst.opcode = OP_NEG_I64;
            }
            // Typed I64 arithmetic
            else if (strcmp(tok, "ADD_I64") == 0) {
                inst.opcode = OP_ADD_I64;
            } else if (strcmp(tok, "SUB_I64") == 0) {
                inst.opcode = OP_SUB_I64;
            } else if (strcmp(tok, "MUL_I64") == 0) {
                inst.opcode = OP_MUL_I64;
            } else if (strcmp(tok, "DIV_I64") == 0) {
                inst.opcode = OP_DIV_I64;
            } else if (strcmp(tok, "MOD_I64") == 0) {
                inst.opcode = OP_MOD_I64;
            } else if (strcmp(tok, "NEG_I64") == 0) {
                inst.opcode = OP_NEG_I64;
            }
            // Typed F32 arithmetic
            else if (strcmp(tok, "ADD_F32") == 0) {
                inst.opcode = OP_ADD_F64;
            } else if (strcmp(tok, "SUB_F32") == 0) {
                inst.opcode = OP_SUB_F64;
            } else if (strcmp(tok, "MUL_F32") == 0) {
                inst.opcode = OP_MUL_F64;
            } else if (strcmp(tok, "DIV_F32") == 0) {
                inst.opcode = OP_DIV_F64;
            } else if (strcmp(tok, "NEG_F32") == 0) {
                inst.opcode = OP_NEG_F64;
            }
            // Typed F64 arithmetic
            else if (strcmp(tok, "ADD_F64") == 0) {
                inst.opcode = OP_ADD_F64;
            } else if (strcmp(tok, "SUB_F64") == 0) {
                inst.opcode = OP_SUB_F64;
            } else if (strcmp(tok, "MUL_F64") == 0) {
                inst.opcode = OP_MUL_F64;
            } else if (strcmp(tok, "DIV_F64") == 0) {
                inst.opcode = OP_DIV_F64;
            } else if (strcmp(tok, "NEG_F64") == 0) {
                inst.opcode = OP_NEG_F64;
            }
            // Typed I32 comparisons
            else if (strcmp(tok, "EQ_I32") == 0) {
                inst.opcode = OP_EQ_I64;
            } else if (strcmp(tok, "NE_I32") == 0) {
                inst.opcode = OP_NE_I64;
            } else if (strcmp(tok, "LT_I32") == 0) {
                inst.opcode = OP_LT_I64;
            } else if (strcmp(tok, "GT_I32") == 0) {
                inst.opcode = OP_GT_I64;
            } else if (strcmp(tok, "LE_I32") == 0) {
                inst.opcode = OP_LE_I64;
            } else if (strcmp(tok, "GE_I32") == 0) {
                inst.opcode = OP_GE_I64;
            }
            // Typed I64 comparisons
            else if (strcmp(tok, "EQ_I64") == 0) {
                inst.opcode = OP_EQ_I64;
            } else if (strcmp(tok, "NE_I64") == 0) {
                inst.opcode = OP_NE_I64;
            } else if (strcmp(tok, "LT_I64") == 0) {
                inst.opcode = OP_LT_I64;
            } else if (strcmp(tok, "GT_I64") == 0) {
                inst.opcode = OP_GT_I64;
            } else if (strcmp(tok, "LE_I64") == 0) {
                inst.opcode = OP_LE_I64;
            } else if (strcmp(tok, "GE_I64") == 0) {
                inst.opcode = OP_GE_I64;
            }
            // Typed F32 comparisons
            else if (strcmp(tok, "EQ_F32") == 0) {
                inst.opcode = OP_EQ_F64;
            } else if (strcmp(tok, "NE_F32") == 0) {
                inst.opcode = OP_NE_F64;
            } else if (strcmp(tok, "LT_F32") == 0) {
                inst.opcode = OP_LT_F64;
            } else if (strcmp(tok, "GT_F32") == 0) {
                inst.opcode = OP_GT_F64;
            } else if (strcmp(tok, "LE_F32") == 0) {
                inst.opcode = OP_LE_F64;
            } else if (strcmp(tok, "GE_F32") == 0) {
                inst.opcode = OP_GE_F64;
            }
            // Typed F64 comparisons
            else if (strcmp(tok, "EQ_F64") == 0) {
                inst.opcode = OP_EQ_F64;
            } else if (strcmp(tok, "NE_F64") == 0) {
                inst.opcode = OP_NE_F64;
            } else if (strcmp(tok, "LT_F64") == 0) {
                inst.opcode = OP_LT_F64;
            } else if (strcmp(tok, "GT_F64") == 0) {
                inst.opcode = OP_GT_F64;
            } else if (strcmp(tok, "LE_F64") == 0) {
                inst.opcode = OP_LE_F64;
            } else if (strcmp(tok, "GE_F64") == 0) {
                inst.opcode = OP_GE_F64;
            }
            // Explicit boolean operations
            else if (strcmp(tok, "AND_BOOL") == 0) {
                inst.opcode = OP_AND_BOOL;
            } else if (strcmp(tok, "OR_BOOL") == 0) {
                inst.opcode = OP_OR_BOOL;
            } else if (strcmp(tok, "NOT_BOOL") == 0) {
                inst.opcode = OP_NOT_BOOL;
            }
            // Additional control flow
            else if (strcmp(tok, "JUMP_IF_TRUE") == 0) {
                inst.opcode = OP_JUMP_IF_TRUE;
                text_next_token(&scanner, tok, sizeof(tok));
                inst.operand.jump.target = (uint32_t)strtoul(tok, NULL, 10);
            }
            // Typed print operations
            else if (strcmp(tok, "PRINT_I32") == 0) {
                inst.opcode = OP_PRINT_I64;
            } else if (strcmp(tok, "PRINT_I64") == 0) {
                inst.opcode = OP_PRINT_I64;
            } else if (strcmp(tok, "PRINT_F32") == 0) {
                inst.opcode = OP_PRINT_F64;
            } else if (strcmp(tok, "PRINT_F64") == 0) {
                inst.opcode = OP_PRINT_F64;
            }
            // Type conversion operations
            else if (strcmp(tok, "CAST_I32_I64") == 0) {
                inst.opcode = OP_CAST_I64_F64;
            } else if (strcmp(tok, "CAST_I64_I32") == 0) {
                inst.opcode = OP_CAST_I64_F64;
            } else if (strcmp(tok, "CAST_F32_F64") == 0) {
                inst.opcode = OP_CAST_F64_I64;
            } else if (strcmp(tok, "CAST_F64_F32") == 0) {
                inst.opcode = OP_CAST_F64_I64;
            } else if (strcmp(tok, "CAST_I32_F32") == 0) {
                inst.opcode = OP_CAST_I64_F64;
            } else if (strcmp(tok, "CAST_I32_F64") == 0) {
                inst.opcode = OP_CAST_I64_F64;
            } else if (strcmp(tok, "CAST_I64_F32") == 0) {
                inst.opcode = OP_CAST_I64_F64;
            } else if (strcmp(tok, "CAST_I64_F64") == 0) {
                inst.opcode = OP_CAST_I64_F64;
            } else if (strcmp(tok, "CAST_F32_I32") == 0) {
                inst.opcode = OP_CAST_F64_I64;
            } else if (strcmp(tok, "CAST_F32_I64") == 0) {
                inst.opcode = OP_CAST_F64_I64;
            } else if (strcmp(tok, "CAST_F64_I32") == 0) {
                inst.opcode = OP_CAST_F64_I64;
            } else if (strcmp(tok, "CAST_F64_I64") == 0) {
                inst.opcode = OP_CAST_F64_I64;
            } else {
                free(buffer);
                bytecode_program_free(program);
                return NULL;
            }

            bytecode_emit(program, inst);
        }

        free(buffer);
        return program;
    }

    fseek(f, 0, SEEK_SET);

    // Check magic number
    uint32_t magic;
    fread(&magic, sizeof(uint32_t), 1, f);
    if (magic != 0x4149534C) {
        fprintf(stderr, "Error: Invalid bytecode file\n");
        fclose(f);
        return NULL;
    }

    BytecodeProgram* program = malloc(sizeof(BytecodeProgram));

    // Read instructions
    fread(&program->instruction_count, sizeof(uint32_t), 1, f);
    program->instruction_capacity = program->instruction_count;
    program->instructions = malloc(sizeof(Instruction) * program->instruction_capacity);
    fread(program->instructions, sizeof(Instruction), program->instruction_count, f);

    // Read string constants
    fread(&program->string_count, sizeof(uint32_t), 1, f);
    program->string_capacity = program->string_count;
    program->string_constants = malloc(sizeof(char*) * program->string_capacity);
    for (uint32_t i = 0; i < program->string_count; i++) {
        uint32_t len;
        fread(&len, sizeof(uint32_t), 1, f);
        program->string_constants[i] = malloc(len + 1);
        fread(program->string_constants[i], 1, len, f);
        program->string_constants[i][len] = '\0';
    }

    // Read functions
    fread(&program->function_count, sizeof(uint32_t), 1, f);
    program->function_capacity = program->function_count;
    program->functions = malloc(sizeof(Function) * program->function_capacity);
    for (uint32_t i = 0; i < program->function_count; i++) {
        uint32_t len;
        fread(&len, sizeof(uint32_t), 1, f);
        program->functions[i].name = malloc(len + 1);
        fread(program->functions[i].name, 1, len, f);
        program->functions[i].name[len] = '\0';
        fread(&program->functions[i].start_addr, sizeof(uint32_t), 1, f);
        fread(&program->functions[i].local_count, sizeof(uint32_t), 1, f);
    }

    fclose(f);
    return program;
}