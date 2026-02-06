#ifndef PARSER_H
#define PARSER_H

#include "lexer.h"
#include "ast.h"

typedef struct {
    Lexer* lexer;
    Token current;
    Token peek_tok;
    bool has_error;
    char error_msg[256];
    char error_code[64];  // Machine-readable error code
} Parser;

void parser_init(Parser* parser, Lexer* lexer);
Module* parser_parse_module(Parser* parser);
Expr* parser_parse_expr(Parser* parser);
Type* parser_parse_type(Parser* parser);

#endif // PARSER_H
