#ifndef BYTECODE_H
#define BYTECODE_H

#include <stdint.h>
#include <stdbool.h>

// BYTECODE INSTRUCTION SET

typedef enum {
    // Stack operations (v6.0 - simplified to int/float only)
    OP_PUSH_INT,      // Push integer constant (64-bit)
    OP_PUSH_FLOAT,    // Push float constant (64-bit)
    OP_PUSH_STRING,   // Push string constant
    OP_PUSH_BOOL,     // Push boolean constant
    OP_PUSH_DECIMAL,  // Push decimal constant (string representation)
    OP_PUSH_UNIT,     // Push unit value
    OP_POP,           // Pop top of stack
    OP_DUP,           // Duplicate top of stack

    // Local variables
    OP_LOAD_LOCAL,    // Load local variable to stack
    OP_STORE_LOCAL,   // Store top of stack to local variable
    OP_LOAD_GLOBAL,   // Load global variable
    OP_STORE_GLOBAL,  // Store global variable

    // Arithmetic - int (i64)
    OP_ADD_INT,
    OP_SUB_INT,
    OP_MUL_INT,
    OP_DIV_INT,
    OP_MOD_INT,
    OP_NEG_INT,

    // Arithmetic - float (f64)
    OP_ADD_FLOAT,
    OP_SUB_FLOAT,
    OP_MUL_FLOAT,
    OP_DIV_FLOAT,
    OP_NEG_FLOAT,

    // Arithmetic - decimal (arbitrary precision)
    OP_ADD_DECIMAL,
    OP_SUB_DECIMAL,
    OP_MUL_DECIMAL,
    OP_DIV_DECIMAL,
    OP_NEG_DECIMAL,

    // Comparison - int (i64)
    OP_EQ_INT,
    OP_NE_INT,
    OP_LT_INT,
    OP_GT_INT,
    OP_LE_INT,
    OP_GE_INT,

    // Comparison - float (f64)
    OP_EQ_FLOAT,
    OP_NE_FLOAT,
    OP_LT_FLOAT,
    OP_GT_FLOAT,
    OP_LE_FLOAT,
    OP_GE_FLOAT,

    // Comparison - decimal
    OP_EQ_DECIMAL,
    OP_NE_DECIMAL,
    OP_LT_DECIMAL,
    OP_GT_DECIMAL,
    OP_LE_DECIMAL,
    OP_GE_DECIMAL,

    // Comparison - string
    OP_EQ_STR,
    OP_NE_STR,

    // Comparison - bool
    OP_EQ_BOOL,
    OP_NE_BOOL,

    // Logical
    OP_AND_BOOL,
    OP_OR_BOOL,
    OP_NOT_BOOL,

    // Type conversions (v6.0 - simplified to int/float only)
    OP_CAST_INT_FLOAT,     // int -> float
    OP_CAST_FLOAT_INT,     // float -> int
    OP_CAST_INT_DECIMAL,   // int -> decimal
    OP_CAST_DECIMAL_INT,   // decimal -> int
    OP_CAST_FLOAT_DECIMAL, // float -> decimal
    OP_CAST_DECIMAL_FLOAT, // decimal -> float
    OP_STR_FROM_DECIMAL,   // decimal -> string

    // Math functions
    OP_MATH_SQRT_FLOAT,  // Square root (float only)
    OP_MATH_POW_FLOAT,   // Power (float only): base exp -> result
    OP_MATH_ABS_INT,     // Absolute value for int
    OP_MATH_ABS_FLOAT,   // Absolute value for float
    OP_MATH_MIN_INT,     // Minimum of two ints
    OP_MATH_MIN_FLOAT,   // Minimum of two floats
    OP_MATH_MAX_INT,     // Maximum of two ints
    OP_MATH_MAX_FLOAT,   // Maximum of two floats

    // Control flow
    OP_JUMP,          // Unconditional jump
    OP_JUMP_IF_FALSE, // Conditional jump
    OP_JUMP_IF_TRUE,  // Conditional jump (added for v4.0)
    OP_CALL,          // Call function
    OP_RETURN,        // Return from function

    // I/O
    OP_IO_WRITE,      // Write to file descriptor
    OP_IO_READ,       // Read from file descriptor
    OP_IO_OPEN,       // Open file, returns handle
    OP_IO_CLOSE,      // Close file handle

    // Standard Input
    OP_STDIN_READ,    // Read line from stdin: -> string
    OP_STDIN_READ_ALL, // Read all available stdin: -> string

    // String (primitives only - high-level ops moved to stdlib/core/string_utils.aisl)
    OP_STR_LEN,
    OP_STR_CONCAT,
    OP_STR_SLICE,
    OP_STR_GET,
    OP_STR_FROM_INT,    // Convert int to string
    OP_STR_FROM_FLOAT,  // Convert float to string

    // Array
    OP_ARRAY_NEW,
    OP_ARRAY_PUSH,
    OP_ARRAY_GET,
    OP_ARRAY_SET,
    OP_ARRAY_LEN,

    // Map/Dictionary
    OP_MAP_NEW,       // Create new empty map
    OP_MAP_SET,       // Set key-value pair: map key value -> map
    OP_MAP_GET,       // Get value by key: map key -> value
    OP_MAP_HAS,       // Check if key exists: map key -> bool
    OP_MAP_DELETE,    // Delete key: map key -> map
    OP_MAP_LEN,       // Get number of entries: map -> int
    OP_MAP_KEYS,      // Get array of keys: map -> array

    // JSON Operations - REMOVED: Now in stdlib/data/json.aisl (uses map primitives)
    // Result Type Operations - REMOVED: Result type removed for LLM simplicity

    // File System Operations
    OP_FILE_READ,         // Read file contents: path -> string
    OP_FILE_WRITE,        // Write file contents: path content -> bool
    OP_FILE_APPEND,       // Append to file: path content -> bool
    OP_FILE_EXISTS,       // Check if file exists: path -> bool
    OP_FILE_DELETE,       // Delete file: path -> bool
    OP_FILE_SIZE,         // Get file size: path -> i64
    OP_FILE_MTIME,        // Get file modification time: path -> i64
    OP_DIR_LIST,          // List directory: path -> array
    OP_DIR_CREATE,        // Create directory: path -> bool
    OP_DIR_DELETE,        // Delete directory: path -> bool

    // Regular Expression Operations
    OP_REGEX_COMPILE,     // Compile regex: pattern -> regex
    OP_REGEX_MATCH,       // Test if string matches: regex text -> bool
    OP_REGEX_FIND,        // Find first match: regex text -> string
    OP_REGEX_FIND_ALL,    // Find all matches: regex text -> array
    OP_REGEX_REPLACE,     // Replace matches: regex text replacement -> string

    // Cryptography Operations
    OP_CRYPTO_SHA256,     // SHA-256 hash: string -> string
    OP_CRYPTO_MD5,        // MD5 hash: string -> string
    OP_CRYPTO_HMAC_SHA256, // HMAC-SHA256: key message -> string

    // Base64 Operations - REMOVED: Now in stdlib/data/base64.aisl (pure AISL implementation)

    // Date/Time Operations
    OP_TIME_NOW,          // Get current Unix timestamp: -> i64
    OP_TIME_FORMAT,       // Format timestamp: i64 format -> string
    OP_TIME_PARSE,        // Parse time string: string format -> i64

    // Process Operations
    OP_PROCESS_SPAWN,     // Spawn process: command args -> process
    OP_PROCESS_EXEC,      // Execute and wait: command args -> int
    OP_PROCESS_WAIT,      // Wait for process: process -> int
    OP_PROCESS_KILL,      // Kill process: process signal -> bool
    OP_PROCESS_PIPE,      // Create pipe: -> [read_fd, write_fd]
    OP_PROCESS_READ,      // Read from process stdout: process -> string
    OP_PROCESS_WRITE,     // Write to process stdin: process data -> bool

    // Network Socket Operations
    OP_TCP_LISTEN,        // Listen on port: port -> socket
    OP_TCP_ACCEPT,        // Accept connection: socket -> socket
    OP_TCP_CONNECT,       // Connect to host:port: host port -> socket
    OP_TCP_TLS_CONNECT,   // Connect with TLS: host port -> socket
    OP_TCP_SEND,          // Send data: socket data -> int
    OP_TCP_RECEIVE,       // Receive data: socket max_bytes -> string
    OP_TCP_CLOSE,         // Close socket: socket -> unit
    OP_UDP_SOCKET,        // Create UDP socket: -> socket
    OP_UDP_BIND,          // Bind UDP socket: socket port -> bool
    OP_UDP_SEND_TO,       // Send to address: socket data host port -> int
    OP_UDP_RECEIVE_FROM,  // Receive from: socket max_bytes -> [data, host, port]

    // Async/Await Operations
    OP_ASYNC_CREATE,      // Create async task: function -> future
    OP_ASYNC_AWAIT,       // Await future: future -> value
    OP_ASYNC_SLEEP,       // Sleep milliseconds: i64 -> unit
    OP_ASYNC_SPAWN,       // Spawn async task: function -> future
    OP_ASYNC_SELECT,      // Select first completed: [futures] -> value

    // Garbage Collection
    OP_GC_COLLECT,        // Trigger GC: -> unit
    OP_GC_STATS,          // Get GC stats: -> map

    // Concurrency
    OP_SPAWN,         // Spawn new thread
    OP_CHANNEL_NEW,   // Create channel
    OP_CHANNEL_SEND,  // Send to channel
    OP_CHANNEL_RECV,  // Receive from channel

    // System
    OP_HALT,          // Stop execution
    OP_PRINT_DEBUG,   // Debug print top of stack
    OP_PRINT_INT,     // Print int
    OP_PRINT_FLOAT,   // Print float
    OP_PRINT_STR,     // Print string
    OP_PRINT_BOOL,    // Print boolean
    OP_PRINT_DECIMAL, // Print decimal
    OP_PRINT_ARRAY,   // Print array (for debugging)
    OP_PRINT_MAP,     // Print map (for debugging)

    // FFI (Foreign Function Interface) Operations
    OP_FFI_LOAD,      // Load native library: library_name -> handle (0 on failure)
    OP_FFI_CALL,      // Call C function: handle func_name arg1 arg2 ... argN arg_count -> result
    OP_FFI_AVAILABLE, // Check if library is available: library_name -> bool
    OP_FFI_CLOSE,     // Close library: handle -> unit

    // Legacy compatibility aliases (v6.0 - map old names to new simplified names)
    OP_ADD_I64 = OP_ADD_INT,
    OP_SUB_I64 = OP_SUB_INT,
    OP_MUL_I64 = OP_MUL_INT,
    OP_DIV_I64 = OP_DIV_INT,
    OP_MOD_I64 = OP_MOD_INT,
    OP_NEG_I64 = OP_NEG_INT,
    OP_EQ_I64 = OP_EQ_INT,
    OP_NEQ_INT = OP_NE_INT,
    OP_NE_I64 = OP_NE_INT,
    OP_LT_I64 = OP_LT_INT,
    OP_GT_I64 = OP_GT_INT,
    OP_LTE_INT = OP_LE_INT,
    OP_LE_I64 = OP_LE_INT,
    OP_GTE_INT = OP_GE_INT,
    OP_GE_I64 = OP_GE_INT,
    OP_ADD_F64 = OP_ADD_FLOAT,
    OP_SUB_F64 = OP_SUB_FLOAT,
    OP_MUL_F64 = OP_MUL_FLOAT,
    OP_DIV_F64 = OP_DIV_FLOAT,
    OP_NEG_F64 = OP_NEG_FLOAT,
    OP_EQ_F64 = OP_EQ_FLOAT,
    OP_NE_F64 = OP_NE_FLOAT,
    OP_LT_F64 = OP_LT_FLOAT,
    OP_GT_F64 = OP_GT_FLOAT,
    OP_LE_F64 = OP_LE_FLOAT,
    OP_GE_F64 = OP_GE_FLOAT,
    OP_CAST_I64_F64 = OP_CAST_INT_FLOAT,
    OP_CAST_F64_I64 = OP_CAST_FLOAT_INT,
    OP_MATH_SQRT_F64 = OP_MATH_SQRT_FLOAT,
    OP_MATH_POW_F64 = OP_MATH_POW_FLOAT,
    OP_MATH_ABS_I64 = OP_MATH_ABS_INT,
    OP_MATH_ABS_F64 = OP_MATH_ABS_FLOAT,
    OP_MATH_MIN_I64 = OP_MATH_MIN_INT,
    OP_MATH_MIN_F64 = OP_MATH_MIN_FLOAT,
    OP_MATH_MAX_I64 = OP_MATH_MAX_INT,
    OP_MATH_MAX_F64 = OP_MATH_MAX_FLOAT,
    OP_STR_FROM_I64 = OP_STR_FROM_INT,
    OP_STR_FROM_F64 = OP_STR_FROM_FLOAT,
    OP_PRINT_I64 = OP_PRINT_INT,
    OP_PRINT_F64 = OP_PRINT_FLOAT,
    OP_AND = OP_AND_BOOL,
    OP_OR = OP_OR_BOOL,
    OP_NOT = OP_NOT_BOOL,
} OpCode;

typedef struct {
    OpCode opcode;
    union {
        int64_t int_val;
        uint32_t uint_val;
        double float_val;    // For float (f64) constants
        char* string_val;
        bool bool_val;
        struct {
            uint32_t target;
        } jump;
        struct {
            uint32_t func_idx;
            uint32_t arg_count;
        } call;
    } operand;
} Instruction;

// BYTECODE PROGRAM

typedef struct {
    char* name;
    uint32_t start_addr;
    uint32_t local_count;
    uint32_t param_count;  // Number of parameters (subset of local_count)
} Function;

typedef struct {
    Instruction* instructions;
    uint32_t instruction_count;
    uint32_t instruction_capacity;

    Function* functions;
    uint32_t function_count;
    uint32_t function_capacity;

    char** string_constants;
    uint32_t string_count;
    uint32_t string_capacity;
} BytecodeProgram;

// BYTECODE PROGRAM FUNCTIONS

BytecodeProgram* bytecode_program_new();
void bytecode_program_free(BytecodeProgram* program);
uint32_t bytecode_emit(BytecodeProgram* program, Instruction inst);
uint32_t bytecode_add_string(BytecodeProgram* program, const char* str);
uint32_t bytecode_add_function(BytecodeProgram* program, const char* name, uint32_t local_count, uint32_t param_count);
uint32_t bytecode_declare_function(BytecodeProgram* program, const char* name, uint32_t local_count, uint32_t param_count);
void bytecode_set_function_start(BytecodeProgram* program, uint32_t idx, uint32_t start_addr);
void bytecode_set_function_locals(BytecodeProgram* program, uint32_t idx, uint32_t local_count, uint32_t param_count);
void bytecode_patch_jump(BytecodeProgram* program, uint32_t offset, uint32_t target);

// Serialization
void bytecode_save(BytecodeProgram* program, const char* filename);
BytecodeProgram* bytecode_load(const char* filename);

#endif
