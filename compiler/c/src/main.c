#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lexer.h"
#include "parser.h"
#include "codegen.h"

char* read_file(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "Error: Cannot open file %s\n", path);
        return NULL;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    char* content = malloc(size + 1);
    fread(content, 1, size, f);
    content[size] = '\0';

    fclose(f);
    return content;
}

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <input.aisl> <output.c>\n", argv[0]);
        return 1;
    }

    const char* input_path = argv[1];
    const char* output_path = argv[2];

    // Read source file
    char* source = read_file(input_path);
    if (!source) {
        return 1;
    }

    // Lex and parse
    Lexer lexer;
    lexer_init(&lexer, source);

    Parser parser;
    parser_init(&parser, &lexer);

    Module* module = parser_parse_module(&parser);

    if (parser.has_error) {
        fprintf(stderr, "%s\n", parser.error_msg);
        free(source);
        return 1;
    }

    // Generate C code
    FILE* output = fopen(output_path, "w");
    if (!output) {
        fprintf(stderr, "Error: Cannot create output file %s\n", output_path);
        free(source);
        return 1;
    }

    Codegen gen;
    codegen_init(&gen, output);
    codegen_module(&gen, module);

    fclose(output);
    free(source);
    free_module(module);

    printf("Compilation successful: %s -> %s\n", input_path, output_path);
    return 0;
}
