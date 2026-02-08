#ifndef LEXER_H
#define LEXER_H

#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>

typedef enum {
    TOK_LPAREN,      // (
    TOK_RPAREN,      // )
    TOK_LBRACKET,    // [
    TOK_RBRACKET,    // ]
    TOK_COLON,       // :
    TOK_COMMA,       // ,
    TOK_ARROW,       // ->
    TOK_EQUAL,       // =

    TOK_IDENTIFIER,
    TOK_INT,
    TOK_FLOAT,
    TOK_STRING,
    TOK_TRUE,
    TOK_FALSE,

    // Keywords
    TOK_MODULE,
    TOK_IMPORT,
    TOK_EXPORT,
    TOK_DEF_FN,
    TOK_DEF_CONST,
    TOK_LET,
    TOK_IN,
    TOK_IF,
    TOK_THEN,
    TOK_ELSE,
    TOK_MATCH,
    TOK_LAMBDA,
    TOK_APPLY,
    TOK_VAR,
    TOK_LIT_INT,
    TOK_LIT_STRING,
    TOK_LIT_BOOL,
    TOK_LIT_UNIT,
    TOK_ADD,
    TOK_SUB,
    TOK_MUL,
    TOK_DIV,
    TOK_EQ,
    TOK_LT,
    TOK_GT,
    TOK_LTE,
    TOK_GTE,
    TOK_SEQ,
    TOK_SPAWN,
    TOK_AWAIT,
    TOK_CHANNEL_NEW,
    TOK_CHANNEL_SEND,
    TOK_CHANNEL_RECV,
    TOK_IO_OPEN,
    TOK_IO_READ,
    TOK_IO_WRITE,
    TOK_IO_CLOSE,
    TOK_WHILE,
    TOK_DO,
    TOK_FOR,
    TOK_LOOP,
    TOK_BREAK,
    TOK_CONTINUE,

    // V3 Keywords
    TOK_DEFS,
    TOK_FN,
    TOK_CALL,
    TOK_SET,
    TOK_GOTO,
    TOK_LABEL,
    TOK_RET,
    TOK_OP,

    // Types (v4.2 - lowercase only)
    TOK_TYPE_STRING,
    TOK_TYPE_BOOL,
    TOK_TYPE_UNIT,
    
    // Simple types (v6.0 - simplified to int/float only)
    TOK_TYPE_INT,      // Maps to i64 (the only integer type for users)
    TOK_TYPE_FLOAT,    // Maps to f64 (the only float type for users)
    
    // Internal only (kept for backward compat in compiler internals)
    TOK_TYPE_I64,      // Internal use only - use TOK_TYPE_INT instead
    TOK_TYPE_F64,      // Internal use only - use TOK_TYPE_FLOAT instead
    
    // Additional v4.0 types
    TOK_TYPE_ARRAY,
    TOK_TYPE_MAP,
    
    // v4.4 JSON type
    TOK_TYPE_JSON,
    
    // v7.0 Concurrency types
    TOK_TYPE_CHANNEL,
    TOK_TYPE_FUTURE,

    // Test framework keywords
    TOK_TEST_SPEC,
    TOK_PROPERTY_SPEC,
    TOK_META_NOTE,
    TOK_CASE,
    TOK_PROPERTY,
    TOK_INPUT,
    TOK_EXPECT,
    TOK_SETUP,
    TOK_MOCK,
    TOK_FORALL,
    TOK_CONSTRAINT,
    TOK_ASSERT,
    TOK_ASSERT_FAIL,
    TOK_MATCH_RESULT,
    TOK_MATCH_OPTION,
    TOK_OK,
    TOK_ERR,
    TOK_SOME,
    TOK_NONE,

    TOK_EOF,
    TOK_ERROR,
} TokenKind;

typedef struct {
    TokenKind kind;
    union {
        char* string_val;
        int64_t int_val;
        double float_val;
    } value;
    int line;
    int column;
} Token;

typedef struct {
    const char* source;
    size_t pos;
    size_t length;
    int line;
    int column;
} Lexer;

void lexer_init(Lexer* lexer, const char* source);
Token lexer_next(Lexer* lexer);
void token_free(Token* token);

#endif // LEXER_H
