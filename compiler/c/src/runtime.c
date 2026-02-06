#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

// ============================================
// VALUE CONSTRUCTORS
// ============================================

Value* value_int(int64_t val) {
    Value* v = malloc(sizeof(Value));
    v->kind = VAL_INT;
    v->data.int_val = val;
    return v;
}

Value* value_string(const char* val) {
    Value* v = malloc(sizeof(Value));
    v->kind = VAL_STRING;
    v->data.string_val = strdup(val);
    return v;
}

Value* value_bool(bool val) {
    Value* v = malloc(sizeof(Value));
    v->kind = VAL_BOOL;
    v->data.bool_val = val;
    return v;
}

Value* value_unit() {
    Value* v = malloc(sizeof(Value));
    v->kind = VAL_UNIT;
    return v;
}

// ============================================
// CHANNEL IMPLEMENTATION
// ============================================

Channel* channel_new(int capacity) {
    Channel* ch = malloc(sizeof(Channel));
    ch->buffer = malloc(sizeof(Value*) * capacity);
    ch->capacity = capacity;
    ch->size = 0;
    ch->read_pos = 0;
    ch->write_pos = 0;
    pthread_mutex_init(&ch->mutex, NULL);
    pthread_cond_init(&ch->not_empty, NULL);
    pthread_cond_init(&ch->not_full, NULL);
    return ch;
}

void channel_send(Channel* ch, Value* val) {
    pthread_mutex_lock(&ch->mutex);

    while (ch->size == ch->capacity) {
        pthread_cond_wait(&ch->not_full, &ch->mutex);
    }

    ch->buffer[ch->write_pos] = val;
    ch->write_pos = (ch->write_pos + 1) % ch->capacity;
    ch->size++;

    pthread_cond_signal(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
}

Value* channel_recv(Channel* ch) {
    pthread_mutex_lock(&ch->mutex);

    while (ch->size == 0) {
        pthread_cond_wait(&ch->not_empty, &ch->mutex);
    }

    Value* val = ch->buffer[ch->read_pos];
    ch->read_pos = (ch->read_pos + 1) % ch->capacity;
    ch->size--;

    pthread_cond_signal(&ch->not_full);
    pthread_mutex_unlock(&ch->mutex);

    return val;
}

void channel_close(Channel* ch) {
    pthread_mutex_destroy(&ch->mutex);
    pthread_cond_destroy(&ch->not_empty);
    pthread_cond_destroy(&ch->not_full);
    free(ch->buffer);
    free(ch);
}

// ============================================
// FUTURE IMPLEMENTATION
// ============================================

Future* future_new() {
    Future* fut = malloc(sizeof(Future));
    fut->value = NULL;
    fut->completed = false;
    pthread_mutex_init(&fut->mutex, NULL);
    pthread_cond_init(&fut->cond, NULL);
    return fut;
}

void future_complete(Future* fut, Value* val) {
    pthread_mutex_lock(&fut->mutex);
    fut->value = val;
    fut->completed = true;
    pthread_cond_broadcast(&fut->cond);
    pthread_mutex_unlock(&fut->mutex);
}

Value* future_await(Future* fut) {
    pthread_mutex_lock(&fut->mutex);

    while (!fut->completed) {
        pthread_cond_wait(&fut->cond, &fut->mutex);
    }

    Value* val = fut->value;
    pthread_mutex_unlock(&fut->mutex);

    return val;
}

// ============================================
// THREADING
// ============================================

void* spawn_thread(void* (*func)(void*), void* arg) {
    pthread_t thread;
    pthread_create(&thread, NULL, func, arg);
    pthread_detach(thread);
    return NULL;
}

// ============================================
// RUNTIME INITIALIZATION
// ============================================

void runtime_init() {
    // Initialize any global runtime state
}

void runtime_cleanup() {
    // Cleanup runtime resources
}
