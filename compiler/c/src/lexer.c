#include "lexer.h"
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

void lexer_init(Lexer* lexer, const char* source) {
    lexer->source = source;
    lexer->pos = 0;
    lexer->length = strlen(source);
    lexer->line = 1;
    lexer->column = 1;
}

static char peek(Lexer* lexer) {
    if (lexer->pos >= lexer->length) return '\0';
    return lexer->source[lexer->pos];
}

static char advance(Lexer* lexer) {
    if (lexer->pos >= lexer->length) return '\0';
    char c = lexer->source[lexer->pos++];
    if (c == '\n') {
        lexer->line++;
        lexer->column = 1;
    } else {
        lexer->column++;
    }
    return c;
}

static void skip_whitespace(Lexer* lexer) {
    while (isspace(peek(lexer))) {
        advance(lexer);
    }
}

static Token make_token(TokenKind kind, int line, int column) {
    Token tok;
    tok.kind = kind;
    tok.line = line;
    tok.column = column;
    return tok;
}

static Token read_string(Lexer* lexer) {
    int line = lexer->line;
    int column = lexer->column;
    advance(lexer); // skip opening "

    // Build string with escape sequence processing
    char* buffer = malloc(1024); // reasonable initial size
    size_t len = 0;
    size_t capacity = 1024;

    while (peek(lexer) != '"' && peek(lexer) != '\0') {
        char c = peek(lexer);

        if (c == '\\') {
            advance(lexer);
            char next = peek(lexer);
            switch (next) {
                case 'n': c = '\n'; break;
                case 't': c = '\t'; break;
                case 'r': c = '\r'; break;
                case '\\': c = '\\'; break;
                case '"': c = '"'; break;
                case '0': c = '\0'; break;
                default: c = next; break; // unknown escape, keep as-is
            }
            advance(lexer);
        } else {
            advance(lexer);
        }

        // Grow buffer if needed
        if (len >= capacity - 1) {
            capacity *= 2;
            buffer = realloc(buffer, capacity);
        }
        buffer[len++] = c;
    }

    buffer[len] = '\0';
    advance(lexer); // skip closing "

    Token tok = make_token(TOK_STRING, line, column);
    tok.value.string_val = buffer;
    return tok;
}

static Token read_number(Lexer* lexer) {
    int line = lexer->line;
    int column = lexer->column;

    size_t start = lexer->pos;
    
    // Handle optional minus sign
    if (peek(lexer) == '-') {
        advance(lexer);
    }
    
    while (isdigit(peek(lexer))) {
        advance(lexer);
    }

    if (peek(lexer) == '.') {
        advance(lexer);
        while (isdigit(peek(lexer))) {
            advance(lexer);
        }
        // Float
        Token tok = make_token(TOK_FLOAT, line, column);
        tok.value.float_val = atof(lexer->source + start);
        return tok;
    }

    // Int
    Token tok = make_token(TOK_INT, line, column);
    tok.value.int_val = atoll(lexer->source + start);
    return tok;
}

static Token read_identifier(Lexer* lexer) {
    int line = lexer->line;
    int column = lexer->column;

    size_t start = lexer->pos;
    while (isalnum(peek(lexer)) || peek(lexer) == '_' || peek(lexer) == '-') {
        advance(lexer);
    }

    size_t len = lexer->pos - start;
    char* str = malloc(len + 1);
    memcpy(str, lexer->source + start, len);
    str[len] = '\0';

    // Check keywords
    TokenKind kind = TOK_IDENTIFIER;
    if (strcmp(str, "Module") == 0) kind = TOK_MODULE;
    else if (strcmp(str, "Import") == 0) kind = TOK_IMPORT;
    else if (strcmp(str, "Export") == 0) kind = TOK_EXPORT;
    else if (strcmp(str, "DefFn") == 0) kind = TOK_DEF_FN;
    else if (strcmp(str, "DefConst") == 0) kind = TOK_DEF_CONST;
    else if (strcmp(str, "Let") == 0) kind = TOK_LET;
    else if (strcmp(str, "In") == 0) kind = TOK_IN;
    else if (strcmp(str, "If") == 0) kind = TOK_IF;
    else if (strcmp(str, "Then") == 0) kind = TOK_THEN;
    else if (strcmp(str, "Else") == 0) kind = TOK_ELSE;
    else if (strcmp(str, "Match") == 0) kind = TOK_MATCH;
    else if (strcmp(str, "Lambda") == 0) kind = TOK_LAMBDA;
    else if (strcmp(str, "Apply") == 0) kind = TOK_APPLY;
    else if (strcmp(str, "Var") == 0) kind = TOK_VAR;
    else if (strcmp(str, "LitInt") == 0) kind = TOK_LIT_INT;
    else if (strcmp(str, "LitString") == 0) kind = TOK_LIT_STRING;
    else if (strcmp(str, "LitBool") == 0) kind = TOK_LIT_BOOL;
    else if (strcmp(str, "LitUnit") == 0) kind = TOK_LIT_UNIT;
    else if (strcmp(str, "Add") == 0) kind = TOK_ADD;
    else if (strcmp(str, "Sub") == 0) kind = TOK_SUB;
    else if (strcmp(str, "Mul") == 0) kind = TOK_MUL;
    else if (strcmp(str, "Div") == 0) kind = TOK_DIV;
    else if (strcmp(str, "Eq") == 0) kind = TOK_EQ;
    else if (strcmp(str, "Lt") == 0) kind = TOK_LT;
    else if (strcmp(str, "Gt") == 0) kind = TOK_GT;
    else if (strcmp(str, "Lte") == 0) kind = TOK_LTE;
    else if (strcmp(str, "Gte") == 0) kind = TOK_GTE;
    else if (strcmp(str, "Seq") == 0) kind = TOK_SEQ;
    else if (strcmp(str, "Spawn") == 0) kind = TOK_SPAWN;
    else if (strcmp(str, "Await") == 0) kind = TOK_AWAIT;
    else if (strcmp(str, "ChannelNew") == 0) kind = TOK_CHANNEL_NEW;
    else if (strcmp(str, "ChannelSend") == 0) kind = TOK_CHANNEL_SEND;
    else if (strcmp(str, "ChannelRecv") == 0) kind = TOK_CHANNEL_RECV;
    else if (strcmp(str, "IOOpen") == 0) kind = TOK_IO_OPEN;
    else if (strcmp(str, "IORead") == 0) kind = TOK_IO_READ;
    else if (strcmp(str, "IOWrite") == 0) kind = TOK_IO_WRITE;
    else if (strcmp(str, "IOClose") == 0) kind = TOK_IO_CLOSE;
    else if (strcmp(str, "While") == 0) kind = TOK_WHILE;
    else if (strcmp(str, "Do") == 0) kind = TOK_DO;
    else if (strcmp(str, "for") == 0) kind = TOK_FOR;
    else if (strcmp(str, "while") == 0) kind = TOK_WHILE;
    else if (strcmp(str, "loop") == 0) kind = TOK_LOOP;
    else if (strcmp(str, "break") == 0) kind = TOK_BREAK;
    else if (strcmp(str, "continue") == 0) kind = TOK_CONTINUE;
    else if (strcmp(str, "mod") == 0) kind = TOK_MOD;
    else if (strcmp(str, "defs") == 0) kind = TOK_DEFS;
    else if (strcmp(str, "fn") == 0) kind = TOK_FN;
    else if (strcmp(str, "call") == 0) kind = TOK_CALL;
    else if (strcmp(str, "set") == 0) kind = TOK_SET;
    // Core IR constructs are now handled as regular function calls, not keywords
    // else if (strcmp(str, "goto") == 0) kind = TOK_GOTO;
    // else if (strcmp(str, "label") == 0) kind = TOK_LABEL;
    // else if (strcmp(str, "ifnot") == 0) kind = TOK_IF;
    else if (strcmp(str, "ret") == 0) kind = TOK_RET;
    else if (strcmp(str, "op") == 0) kind = TOK_OP;
    // else if (strcmp(str, "ifnot") == 0) kind = TOK_IF;  // Treat as identifier now
    else if (strcmp(str, "print") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "print_int") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "read_file") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "write_file") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "strlen") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "strcat") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "substr") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "strget") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "array_new") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "array_push") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "array_get") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "array_len") == 0) kind = TOK_IDENTIFIER;
    else if (strcmp(str, "string") == 0) kind = TOK_TYPE_STRING;
    else if (strcmp(str, "bool") == 0) kind = TOK_TYPE_BOOL;
    else if (strcmp(str, "unit") == 0) kind = TOK_TYPE_UNIT;
    else if (strcmp(str, "int") == 0) kind = TOK_TYPE_INT;
    else if (strcmp(str, "float") == 0) kind = TOK_TYPE_FLOAT;
    else if (strcmp(str, "i8") == 0) kind = TOK_TYPE_I8;
    else if (strcmp(str, "i16") == 0) kind = TOK_TYPE_I16;
    else if (strcmp(str, "i32") == 0) kind = TOK_TYPE_I32;
    else if (strcmp(str, "i64") == 0) kind = TOK_TYPE_I64;
    else if (strcmp(str, "u8") == 0) kind = TOK_TYPE_U8;
    else if (strcmp(str, "u16") == 0) kind = TOK_TYPE_U16;
    else if (strcmp(str, "u32") == 0) kind = TOK_TYPE_U32;
    else if (strcmp(str, "u64") == 0) kind = TOK_TYPE_U64;
    else if (strcmp(str, "f32") == 0) kind = TOK_TYPE_F32;
    else if (strcmp(str, "f64") == 0) kind = TOK_TYPE_F64;
    else if (strcmp(str, "array") == 0) kind = TOK_TYPE_ARRAY;
    else if (strcmp(str, "map") == 0) kind = TOK_TYPE_MAP;
    else if (strcmp(str, "json") == 0) kind = TOK_TYPE_JSON;
    else if (strcmp(str, "true") == 0) kind = TOK_TRUE;
    else if (strcmp(str, "false") == 0) kind = TOK_FALSE;
    
    // Test framework keywords
    else if (strcmp(str, "test-spec") == 0) kind = TOK_TEST_SPEC;
    else if (strcmp(str, "property-spec") == 0) kind = TOK_PROPERTY_SPEC;
    else if (strcmp(str, "meta-note") == 0) kind = TOK_META_NOTE;
    else if (strcmp(str, "case") == 0) kind = TOK_CASE;
    else if (strcmp(str, "property") == 0) kind = TOK_PROPERTY;
    else if (strcmp(str, "input") == 0) kind = TOK_INPUT;
    else if (strcmp(str, "expect") == 0) kind = TOK_EXPECT;
    else if (strcmp(str, "setup") == 0) kind = TOK_SETUP;
    else if (strcmp(str, "mock") == 0) kind = TOK_MOCK;
    else if (strcmp(str, "forall") == 0) kind = TOK_FORALL;
    else if (strcmp(str, "constraint") == 0) kind = TOK_CONSTRAINT;
    else if (strcmp(str, "assert") == 0) kind = TOK_ASSERT;
    else if (strcmp(str, "assert-fail") == 0) kind = TOK_ASSERT_FAIL;
    else if (strcmp(str, "match-result") == 0) kind = TOK_MATCH_RESULT;
    else if (strcmp(str, "match-option") == 0) kind = TOK_MATCH_OPTION;
    else if (strcmp(str, "ok") == 0) kind = TOK_OK;
    else if (strcmp(str, "err") == 0) kind = TOK_ERR;
    else if (strcmp(str, "some") == 0) kind = TOK_SOME;
    else if (strcmp(str, "none") == 0) kind = TOK_NONE;

    Token tok = make_token(kind, line, column);
    if (kind == TOK_IDENTIFIER) {
        tok.value.string_val = str;
    } else {
        free(str);
    }
    return tok;
}

Token lexer_next(Lexer* lexer) {
    skip_whitespace(lexer);

    if (lexer->pos >= lexer->length) {
        return make_token(TOK_EOF, lexer->line, lexer->column);
    }

    char c = peek(lexer);
    int line = lexer->line;
    int column = lexer->column;

    if (c == '(') {
        advance(lexer);
        return make_token(TOK_LPAREN, line, column);
    }
    if (c == ')') {
        advance(lexer);
        return make_token(TOK_RPAREN, line, column);
    }
    if (c == '[') {
        advance(lexer);
        return make_token(TOK_LBRACKET, line, column);
    }
    if (c == ']') {
        advance(lexer);
        return make_token(TOK_RBRACKET, line, column);
    }
    if (c == ':') {
        advance(lexer);
        return make_token(TOK_COLON, line, column);
    }
    if (c == ',') {
        advance(lexer);
        return make_token(TOK_COMMA, line, column);
    }
    if (c == '=') {
        advance(lexer);
        return make_token(TOK_EQUAL, line, column);
    }
    if (c == '-') {
        advance(lexer);
        if (peek(lexer) == '>') {
            advance(lexer);
            return make_token(TOK_ARROW, line, column);
        }
        // Negative number
        lexer->pos--;
        lexer->column--;
        return read_number(lexer);
    }
    if (c == '"') {
        return read_string(lexer);
    }
    if (isdigit(c)) {
        return read_number(lexer);
    }
    if (isalpha(c) || c == '_') {
        return read_identifier(lexer);
    }

    advance(lexer);
    return make_token(TOK_ERROR, line, column);
}

void token_free(Token* token) {
    if (token->kind == TOK_STRING || token->kind == TOK_IDENTIFIER) {
        free(token->value.string_val);
    }
}
