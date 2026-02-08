#ifndef VM_H
#define VM_H

#include "bytecode.h"
#include <pthread.h>

#define STACK_SIZE 16777216
#define CALL_STACK_SIZE 65536
#define GC_HEAP_GROW_FACTOR 2

// VALUE SYSTEM

typedef enum {
    VAL_INT,
    VAL_STRING,
    VAL_BOOL,
    VAL_UNIT,
    VAL_CHANNEL,
    VAL_THREAD,
    VAL_ARRAY,
    VAL_MAP,
    VAL_JSON,
    VAL_REGEX,
    VAL_FILE_HANDLE,
    VAL_PROCESS,
    VAL_TCP_SOCKET,
    VAL_UDP_SOCKET,
    VAL_FUTURE,
    
    VAL_I8,
    VAL_I16,
    VAL_I32,
    VAL_I64,
    VAL_U8,
    VAL_U16,
    VAL_U32,
    VAL_U64,
    
    VAL_F32,
    VAL_F64,
    
    VAL_RESULT,
    VAL_FFI_HANDLE,
} ValueType;

// GARBAGE COLLECTION

typedef enum {
    OBJ_STRING,
    OBJ_ARRAY,
    OBJ_MAP,
    OBJ_JSON,
    OBJ_HTTP_RESPONSE,
    OBJ_WEBSOCKET,
    OBJ_REGEX,
    OBJ_PROCESS,
    OBJ_TCP_SOCKET,
    OBJ_UDP_SOCKET,
    OBJ_FUTURE,
    OBJ_RESULT,
    OBJ_FFI_HANDLE,
} ObjType;

typedef struct Obj Obj;

struct Obj {
    ObjType type;
    bool marked;
    struct Obj* next;
    void* data;
};

typedef struct {
    Obj* objects;
    size_t bytes_allocated;
    size_t next_gc;
} GC;

typedef struct {
    ValueType type;
    union {
        // Legacy
        int64_t int_val;        // For VAL_INT (alias to i64_val)
        char* string_val;
        bool bool_val;
        void* ptr_val;
        Obj* obj;               // GC-managed object
        
        // Explicit integer types
        int8_t i8_val;
        int16_t i16_val;
        int32_t i32_val;
        int64_t i64_val;
        uint8_t u8_val;
        uint16_t u16_val;
        uint32_t u32_val;
        uint64_t u64_val;
        
        // Floating point types
        float f32_val;
        double f64_val;
    } data;
} Value;

// CALL FRAME

typedef struct {
    uint32_t return_addr;
    uint32_t frame_pointer;
    uint32_t local_count;
    uint32_t param_count;
} CallFrame;

// FFI (FOREIGN FUNCTION INTERFACE)

typedef struct FFILibrary {
    char* name;          // Library name (e.g., "libaisl_http")
    void* handle;        // dlopen handle
    struct FFILibrary* next;
} FFILibrary;

// VIRTUAL MACHINE

typedef struct {
    BytecodeProgram* program;

    // Execution state
    uint32_t ip;  // Instruction pointer
    Value* stack;  // Dynamic stack allocation
    uint32_t sp;  // Stack pointer
    size_t stack_capacity;

    // Call stack
    CallFrame* call_stack;  // Dynamic call stack allocation
    uint32_t call_sp;
    size_t call_stack_capacity;

    // Globals
    Value* globals;
    uint32_t global_count;

    // Garbage collector
    GC gc;

    // FFI (Foreign Function Interface)
    FFILibrary* ffi_libraries;

    // Runtime state
    bool running;
    int exit_code;
} VM;

// VM FUNCTIONS

VM* vm_new(BytecodeProgram* program);
void vm_free(VM* vm);
int vm_run(VM* vm);
void vm_disassemble(BytecodeProgram* program);

// GC functions
void gc_init(GC* gc);
void gc_collect(VM* vm);
Obj* gc_alloc_object(VM* vm, ObjType type, size_t size);
void gc_mark_value(Value val);
void gc_mark_all_roots(VM* vm);
void gc_sweep(VM* vm);

#endif
