#ifndef RUNTIME_H
#define RUNTIME_H

#include <stdint.h>
#include <stdbool.h>
#include <pthread.h>

// ============================================
// VALUE REPRESENTATION
// ============================================

typedef enum {
    VAL_INT,
    VAL_FLOAT,
    VAL_STRING,
    VAL_BOOL,
    VAL_UNIT,
    VAL_CLOSURE,
    VAL_CHANNEL,
    VAL_FUTURE,
} ValueKind;

typedef struct Value Value;
typedef struct Closure Closure;
typedef struct Channel Channel;
typedef struct Future Future;

struct Value {
    ValueKind kind;
    union {
        int64_t int_val;
        double float_val;
        char* string_val;
        bool bool_val;
        Closure* closure;
        Channel* channel;
        Future* future;
    } data;
};

struct Closure {
    void* (*func)(Value** args, int argc);
    Value** captured;
    int capture_count;
};

struct Channel {
    Value** buffer;
    int capacity;
    int size;
    int read_pos;
    int write_pos;
    pthread_mutex_t mutex;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
};

struct Future {
    Value* value;
    bool completed;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
};

// ============================================
// RUNTIME FUNCTIONS
// ============================================

Value* value_int(int64_t val);
Value* value_string(const char* val);
Value* value_bool(bool val);
Value* value_unit();

Channel* channel_new(int capacity);
void channel_send(Channel* ch, Value* val);
Value* channel_recv(Channel* ch);
void channel_close(Channel* ch);

Future* future_new();
void future_complete(Future* fut, Value* val);
Value* future_await(Future* fut);

void* spawn_thread(void* (*func)(void*), void* arg);

void runtime_init();
void runtime_cleanup();

#endif // RUNTIME_H
