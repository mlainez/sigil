#ifndef AST_H
#define AST_H

#include <stdint.h>
#include <stdbool.h>

// TYPE DEFINITIONS

typedef enum {
    TYPE_INT,           // Always i64 - only integer type in AISL
    TYPE_FLOAT,         // Always f64 - only float type in AISL
    TYPE_STRING,
    TYPE_BOOL,
    TYPE_UNIT,
    TYPE_BYTES,
    TYPE_GENERIC,
    TYPE_FUNCTION,
    TYPE_TUPLE,
    TYPE_RECORD,
    TYPE_VARIANT,
    TYPE_REF,
    TYPE_LIST,
    TYPE_ARRAY,
    TYPE_OPTION,
    TYPE_RESULT,
    TYPE_FUTURE,
    TYPE_CHANNEL,
    TYPE_MAP,
    TYPE_JSON,
} TypeKind;

typedef struct Type Type;
typedef struct TypeList TypeList;

struct TypeList {
    Type* type;
    TypeList* next;
};

struct Type {
    TypeKind kind;
    union {
        struct {
            TypeList* param_types;
            Type* return_type;
        } func;
        struct {
            TypeList* types;
        } tuple;
        struct {
            Type* element_type;
        } generic;
        struct {
            Type* inner;
        } ref;
    } data;
};

// EXPRESSION DEFINITIONS

typedef enum {
    EXPR_LIT_INT,
    EXPR_LIT_FLOAT,
    EXPR_LIT_STRING,
    EXPR_LIT_BOOL,
    EXPR_LIT_UNIT,
    EXPR_VAR,
    EXPR_LET,
    EXPR_LAMBDA,
    EXPR_APPLY,
    EXPR_IF,
    EXPR_MATCH,
    EXPR_TUPLE,
    EXPR_RECORD,
    EXPR_VARIANT,
    EXPR_ARRAY,
    EXPR_BLOCK,
    EXPR_BINARY,
    EXPR_UNARY,
    EXPR_FIELD,
    EXPR_INDEX,
    EXPR_ASSIGN,
    EXPR_SEQ,
    EXPR_WHILE,
    EXPR_FOR,
    EXPR_RETURN,
    EXPR_BREAK,
    EXPR_CONTINUE,
    EXPR_SPAWN,
    EXPR_AWAIT,
    EXPR_CHANNEL_NEW,
    EXPR_CHANNEL_SEND,
    EXPR_CHANNEL_RECV,
    EXPR_IO_READ,
    EXPR_IO_WRITE,
    EXPR_IO_OPEN,
    EXPR_IO_CLOSE,
    EXPR_REF_NEW,
    EXPR_REF_READ,
    EXPR_REF_WRITE,
    EXPR_TRY,
    EXPR_THROW,
} ExprKind;

typedef enum {
    BIN_ADD, BIN_SUB, BIN_MUL, BIN_DIV, BIN_MOD,
    BIN_EQ, BIN_NEQ, BIN_LT, BIN_GT, BIN_LTE, BIN_GTE,
    BIN_AND, BIN_OR,
    BIN_CONCAT,
} BinaryOp;

typedef enum {
    UN_NEG, UN_NOT,
} UnaryOp;

typedef struct Expr Expr;
typedef struct ExprList ExprList;
typedef struct Binding Binding;
typedef struct BindingList BindingList;
typedef struct Param Param;
typedef struct ParamList ParamList;
typedef struct Pattern Pattern;
typedef struct MatchCase MatchCase;
typedef struct MatchCaseList MatchCaseList;

struct ExprList {
    Expr* expr;
    ExprList* next;
};

struct Binding {
    char* name;
    Type* type;
    Expr* value;
};

struct BindingList {
    Binding* binding;
    BindingList* next;
};

struct Param {
    char* name;
    Type* type;
};

struct ParamList {
    Param* param;
    ParamList* next;
};

struct Pattern {
    enum {
        PAT_LIT_INT,
        PAT_LIT_STRING,
        PAT_LIT_BOOL,
        PAT_WILD,
        PAT_VAR,
        PAT_TUPLE,
        PAT_ARRAY,
        PAT_VARIANT,
    } kind;
    Type* type;
    union {
        int64_t int_val;
        char* string_val;
        bool bool_val;
        struct {
            char* name;
        } var;
        struct {
            Pattern** patterns;
            int count;
        } tuple;
        struct {
            char* constructor;
            Pattern** patterns;
            int count;
        } variant;
    } data;
};

struct MatchCase {
    Pattern* pattern;
    Expr* body;
};

struct MatchCaseList {
    MatchCase* case_item;
    MatchCaseList* next;
};

struct Expr {
    ExprKind kind;
    Type* type;
    union {
        int64_t int_val;
        double float_val;
        char* string_val;
        bool bool_val;
        struct {
            char* name;
        } var;
        struct {
            BindingList* bindings;
            Expr* body;
        } let;
        struct {
            ParamList* params;
            Expr* body;
        } lambda;
        struct {
            Expr* func;
            ExprList* args;
        } apply;
        struct {
            Expr* cond;
            Expr* then_expr;
            Expr* else_expr;
        } if_expr;
        struct {
            Expr* scrutinee;
            MatchCaseList* cases;
        } match;
        struct {
            ExprList* elements;
        } tuple;
        struct {
            ExprList* elements;
        } array;
        struct {
            ExprList* exprs;
        } block;
        struct {
            BinaryOp op;
            Expr* left;
            Expr* right;
        } binary;
        struct {
            UnaryOp op;
            Expr* operand;
        } unary;
        struct {
            Expr* object;
            char* field;
        } field;
        struct {
            Expr* array;
            Expr* index;
        } index;
        struct {
            char* var;
            Expr* value;
        } assign;
        struct {
            ExprList* exprs;
        } seq;
        struct {
            Expr* cond;
            Expr* body;
        } while_loop;
        struct {
            Expr* value;
        } spawn;
        struct {
            Expr* future;
        } await;
        struct {
            int capacity;
        } channel_new;
        struct {
            Expr* channel;
            Expr* value;
        } channel_send;
        struct {
            Expr* channel;
        } channel_recv;
        struct {
            Expr* handle;
        } io_read;
        struct {
            Expr* handle;
            Expr* data;
        } io_write;
        struct {
            Expr* path;
            Expr* mode;
        } io_open;
        struct {
            Expr* handle;
        } io_close;
        struct {
            Expr* value;
        } ref_new;
        struct {
            Expr* ref;
        } ref_read;
        struct {
            Expr* ref;
            Expr* value;
        } ref_write;
        struct {
            Expr* value;
        } return_expr;
    } data;
};

// DEFINITION DEFINITIONS

typedef enum {
    DEF_FUNCTION,
    DEF_CONST,
    DEF_TYPE,
    DEF_TEST_SPEC,
    DEF_PROPERTY_SPEC,
    DEF_META_NOTE,
} DefKind;

typedef struct Definition Definition;
typedef struct DefList DefList;

struct Definition {
    DefKind kind;
    char* name;
    int line;
    union {
        struct {
            ParamList* params;
            Type* return_type;
            Expr* body;
        } func;
        struct {
            Type* type;
            Expr* value;
        } const_def;
        struct {
            void* test_spec;
        } test;
        struct {
            void* property_spec;
        } property;
        struct {
            char* note_text;
        } meta_note;
    } data;
};

struct DefList {
    Definition* def;
    DefList* next;
};

// MODULE DEFINITION

// Import types
typedef enum {
    IMPORT_FULL,      // (import math) - all functions
    IMPORT_SELECTIVE, // (import (math sqrt pow)) - specific functions
    IMPORT_ALIASED    // (import (math :as m)) - with alias
} ImportType;

// Individual import statement
typedef struct {
    char* module_name;        // Module name as string (e.g. "math")
    ImportType type;
    char* alias;              // For IMPORT_ALIASED
    char** functions;         // For IMPORT_SELECTIVE
    int function_count;       // Number of functions in selective import
} Import;

typedef struct Module {
    char* name;
    Import** imports;          // Array of import statements
    int import_count;          // Number of imports
    DefList* definitions;
} Module;

// HELPER FUNCTIONS

Type* type_int();
Type* type_string();
Type* type_bool();
Type* type_unit();
Type* type_function(TypeList* params, Type* ret);
Type* type_channel(Type* element);
Type* type_future(Type* element);
Type* type_float();
Type* type_array(Type* element);
Type* type_map(Type* key, Type* value);
Type* type_json();

// Internal aliases for backward compatibility
Type* type_i64();  // Maps to TYPE_INT
Type* type_f64();  // Maps to TYPE_FLOAT

Expr* expr_lit_int(int64_t val);
Expr* expr_lit_float(double val);
Expr* expr_lit_string(const char* val);
Expr* expr_lit_bool(bool val);
Expr* expr_lit_unit();
Expr* expr_var(const char* name, Type* type);
Expr* expr_binary(BinaryOp op, Expr* left, Expr* right, Type* type);
Expr* expr_apply(Expr* func, ExprList* args, Type* type);
Expr* expr_if(Expr* cond, Expr* then_expr, Expr* else_expr, Type* type);
Expr* expr_seq(ExprList* exprs, Type* type);
Expr* expr_io_write(Expr* handle, Expr* data, Type* type);
Expr* expr_io_read(Expr* handle, Type* type);
Expr* expr_io_open(Expr* path, Expr* mode, Type* type);
Expr* expr_io_close(Expr* handle, Type* type);
Expr* expr_let(BindingList* bindings, Expr* body, Type* type);
Expr* expr_while(Expr* cond, Expr* body, Type* type);
Expr* expr_return(Expr* value, Type* type);

ExprList* expr_list_new(Expr* expr, ExprList* next);
ParamList* param_list_new(const char* name, Type* type, ParamList* next);
BindingList* binding_list_new(const char* name, Type* type, Expr* value, BindingList* next);

void free_expr(Expr* expr);
void free_type(Type* type);
void free_module(Module* mod);

#endif // AST_H
