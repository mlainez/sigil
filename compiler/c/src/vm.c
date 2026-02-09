#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#define OPENSSL_API_COMPAT 0x10100000L
#include "vm.h"
#include "decimal.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <limits.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <regex.h>
#include <signal.h>
#include <poll.h>
#include <dlfcn.h>
#include <openssl/sha.h>
#include <openssl/md5.h>
#include <openssl/hmac.h>
#include <openssl/ssl.h>
#include <openssl/err.h>

typedef struct {
    Value* items;
    uint32_t count;
    uint32_t capacity;
} Array;

// Simple hash map implementation using string keys
typedef struct MapEntry {
    char* key;
    Value value;
    struct MapEntry* next;  // For chaining collisions
} MapEntry;

typedef struct {
    MapEntry** buckets;
    uint32_t bucket_count;
    uint32_t size;  // Number of entries
} Map;

// Result type for error handling
typedef struct {
    bool is_ok;
    union {
        Value ok_value;      // The actual value if Ok
        struct {
            int32_t code;    // Error code
            char* message;   // Error message
        } err;
    } data;
} Result;

// JSON Value types
typedef enum {
    JSON_NULL,
    JSON_BOOL,
    JSON_NUMBER,
    JSON_STRING,
    JSON_ARRAY,
    JSON_OBJECT
} JsonType;

typedef struct JsonValue JsonValue;

typedef struct JsonArrayItem {
    JsonValue* value;
    struct JsonArrayItem* next;
} JsonArrayItem;

typedef struct JsonObjectEntry {
    char* key;
    JsonValue* value;
    struct JsonObjectEntry* next;
} JsonObjectEntry;

struct JsonValue {
    JsonType type;
    union {
        bool bool_val;
        double number_val;
        char* string_val;
        JsonArrayItem* array_items;
        JsonObjectEntry* object_entries;
    } data;
    uint32_t length;
};


typedef struct {
    regex_t compiled;
    char* pattern;
} RegexValue;

typedef struct {
    pid_t pid;
    int stdin_fd;
    int stdout_fd;
    int stderr_fd;
} Process;

typedef struct {
    int sockfd;
    struct sockaddr_in addr;
    bool is_udp;
    bool is_tls;
    SSL* ssl;
    SSL_CTX* ssl_ctx;
} Socket;

typedef struct {
    bool completed;
    Value result;
    pthread_t thread;
} Future;

typedef struct ChannelItem {
    Value value;
    struct ChannelItem* next;
} ChannelItem;

typedef struct {
    ChannelItem* head;
    ChannelItem* tail;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int capacity;
    int size;
} Channel;

// GARBAGE COLLECTOR IMPLEMENTATION

void gc_init(GC* gc) {
    gc->objects = NULL;
    gc->bytes_allocated = 0;
    gc->next_gc = 1024 * 1024;
}

Obj* gc_alloc_object(VM* vm, ObjType type, size_t size) {
    if (vm->gc.bytes_allocated + size > vm->gc.next_gc) {
        gc_collect(vm);
    }
    
    Obj* obj = malloc(sizeof(Obj));
    obj->type = type;
    obj->marked = false;
    obj->data = malloc(size);
    obj->next = vm->gc.objects;
    vm->gc.objects = obj;
    vm->gc.bytes_allocated += size + sizeof(Obj);
    
    return obj;
}

void gc_mark_value(Value val) {
    if (val.type == VAL_ARRAY || val.type == VAL_MAP || val.type == VAL_JSON ||
        val.type == VAL_REGEX || val.type == VAL_PROCESS ||
        val.type == VAL_TCP_SOCKET || val.type == VAL_UDP_SOCKET ||
        val.type == VAL_FUTURE) {
        Obj* obj = val.data.obj;
        if (obj && !obj->marked) {
            obj->marked = true;
            
            if (obj->type == OBJ_ARRAY) {
                Array* arr = (Array*)obj->data;
                for (uint32_t i = 0; i < arr->count; i++) {
                    gc_mark_value(arr->items[i]);
                }
            } else if (obj->type == OBJ_MAP) {
                Map* map = (Map*)obj->data;
                for (uint32_t i = 0; i < map->bucket_count; i++) {
                    MapEntry* entry = map->buckets[i];
                    while (entry) {
                        gc_mark_value(entry->value);
                        entry = entry->next;
                    }
                }
            }
        }
    }
}

void gc_mark_all_roots(VM* vm) {
    for (uint32_t i = 0; i < vm->sp; i++) {
        gc_mark_value(vm->stack[i]);
    }
    
    for (uint32_t i = 0; i < vm->global_count; i++) {
        gc_mark_value(vm->globals[i]);
    }
}

void gc_sweep(VM* vm) {
    Obj** obj_ptr = &vm->gc.objects;
    while (*obj_ptr) {
        if (!(*obj_ptr)->marked) {
            Obj* unreached = *obj_ptr;
            *obj_ptr = unreached->next;
            
            free(unreached->data);
            free(unreached);
            vm->gc.bytes_allocated -= sizeof(Obj);
        } else {
            (*obj_ptr)->marked = false;
            obj_ptr = &(*obj_ptr)->next;
        }
    }
}

void gc_collect(VM* vm) {
    // size_t before = vm->gc.bytes_allocated; // Unused - could be used for GC stats
    
    gc_mark_all_roots(vm);
    gc_sweep(vm);
    
    vm->gc.next_gc = vm->gc.bytes_allocated * GC_HEAP_GROW_FACTOR;
    if (vm->gc.next_gc < 1024 * 1024) {
        vm->gc.next_gc = 1024 * 1024;
    }
}

static uint32_t hash_string(const char* str, uint32_t bucket_count) {
    uint32_t hash = 5381;
    int c;
    while ((c = *str++)) {
        hash = ((hash << 5) + hash) + c;  // hash * 33 + c
    }
    return hash % bucket_count;
}

static Value value_clone(Value val) {
    if (val.type == VAL_STRING) {
        Value copy = val;
        copy.data.string_val = strdup(val.data.string_val);
        return copy;
    }
    if (val.type == VAL_DECIMAL) {
        Value copy = val;
        copy.data.decimal_val = strdup(val.data.decimal_val);
        return copy;
    }
    return val;
}


static char* file_read(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    char* content = malloc(size + 1);
    fread(content, 1, size, f);
    content[size] = '\0';
    fclose(f);
    
    return content;
}

static int file_write(const char* path, const char* content) {
    FILE* f = fopen(path, "wb");
    if (!f) return 0;
    
    size_t len = strlen(content);
    size_t written = fwrite(content, 1, len, f);
    fclose(f);
    
    return written == len;
}

static int file_append(const char* path, const char* content) {
    FILE* f = fopen(path, "ab");
    if (!f) return 0;
    
    size_t len = strlen(content);
    size_t written = fwrite(content, 1, len, f);
    fclose(f);
    
    return written == len;
}

static int file_exists(const char* path) {
    return access(path, F_OK) == 0;
}

static int file_delete(const char* path) {
    return unlink(path) == 0;
}

static int64_t file_size(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return st.st_size;
}

static int64_t file_mtime(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return st.st_mtime;
}

static Array* dir_list(const char* path) {
    DIR* dir = opendir(path);
    if (!dir) return NULL;
    
    Array* arr = malloc(sizeof(Array));
    arr->capacity = 16;
    arr->count = 0;
    arr->items = malloc(sizeof(Value) * arr->capacity);
    
    struct dirent* entry;
    while ((entry = readdir(dir)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
            continue;
        }
        
        if (arr->count >= arr->capacity) {
            arr->capacity *= 2;
            arr->items = realloc(arr->items, sizeof(Value) * arr->capacity);
        }
        
        Value val = {.type = VAL_STRING, .data.string_val = strdup(entry->d_name)};
        arr->items[arr->count++] = val;
    }
    
    closedir(dir);
    return arr;
}

static int dir_create(const char* path) {
    return mkdir(path, 0755) == 0;
}

static int dir_delete(const char* path) {
    return rmdir(path) == 0;
}

static RegexValue* regex_compile(const char* pattern) {
    RegexValue* re = malloc(sizeof(RegexValue));
    re->pattern = strdup(pattern);
    
    if (regcomp(&re->compiled, pattern, REG_EXTENDED) != 0) {
        free(re->pattern);
        free(re);
        return NULL;
    }
    
    return re;
}

static void regex_free(RegexValue* re) __attribute__((unused));
static void regex_free(RegexValue* re) {
    if (!re) return;
    regfree(&re->compiled);
    free(re->pattern);
    free(re);
}

static int regex_match(RegexValue* re, const char* text) {
    return regexec(&re->compiled, text, 0, NULL, 0) == 0;
}

static char* regex_find(RegexValue* re, const char* text) {
    regmatch_t match[1];
    if (regexec(&re->compiled, text, 1, match, 0) == 0) {
        size_t len = match[0].rm_eo - match[0].rm_so;
        char* result = malloc(len + 1);
        memcpy(result, text + match[0].rm_so, len);
        result[len] = '\0';
        return result;
    }
    return strdup("");
}

static Array* regex_find_all(RegexValue* re, const char* text) {
    Array* arr = malloc(sizeof(Array));
    arr->capacity = 16;
    arr->count = 0;
    arr->items = malloc(sizeof(Value) * arr->capacity);
    
    const char* p = text;
    regmatch_t match[1];
    
    while (regexec(&re->compiled, p, 1, match, 0) == 0) {
        size_t len = match[0].rm_eo - match[0].rm_so;
        char* matched = malloc(len + 1);
        memcpy(matched, p + match[0].rm_so, len);
        matched[len] = '\0';
        
        if (arr->count >= arr->capacity) {
            arr->capacity *= 2;
            arr->items = realloc(arr->items, sizeof(Value) * arr->capacity);
        }
        
        Value val = {.type = VAL_STRING, .data.string_val = matched};
        arr->items[arr->count++] = val;
        
        p += match[0].rm_eo;
        if (match[0].rm_eo == 0) break;
    }
    
    return arr;
}

static char* regex_replace(RegexValue* re, const char* text, const char* replacement) {
    size_t cap = 1024;
    size_t len = 0;
    char* result = malloc(cap);
    
    const char* p = text;
    regmatch_t match[1];
    
    while (regexec(&re->compiled, p, 1, match, 0) == 0) {
        size_t prefix_len = match[0].rm_so;
        size_t repl_len = strlen(replacement);
        
        while (len + prefix_len + repl_len + 1 > cap) {
            cap *= 2;
            result = realloc(result, cap);
        }
        
        memcpy(result + len, p, prefix_len);
        len += prefix_len;
        memcpy(result + len, replacement, repl_len);
        len += repl_len;
        
        p += match[0].rm_eo;
        if (match[0].rm_eo == 0) break;
    }
    
    size_t remaining = strlen(p);
    while (len + remaining + 1 > cap) {
        cap *= 2;
        result = realloc(result, cap);
    }
    memcpy(result + len, p, remaining);
    len += remaining;
    result[len] = '\0';
    
    return result;
}

static char* crypto_sha256(const char* input) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256((unsigned char*)input, strlen(input), hash);
    
    char* output = malloc(SHA256_DIGEST_LENGTH * 2 + 1);
    for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        sprintf(output + i * 2, "%02x", hash[i]);
    }
    output[SHA256_DIGEST_LENGTH * 2] = '\0';
    
    return output;
}

static char* crypto_md5(const char* input) {
    unsigned char hash[MD5_DIGEST_LENGTH];
    MD5((unsigned char*)input, strlen(input), hash);
    
    char* output = malloc(MD5_DIGEST_LENGTH * 2 + 1);
    for (int i = 0; i < MD5_DIGEST_LENGTH; i++) {
        sprintf(output + i * 2, "%02x", hash[i]);
    }
    output[MD5_DIGEST_LENGTH * 2] = '\0';
    
    return output;
}

static char* crypto_hmac_sha256(const char* key, const char* message) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    unsigned int len = SHA256_DIGEST_LENGTH;
    
    HMAC(EVP_sha256(), key, strlen(key), 
         (unsigned char*)message, strlen(message), hash, &len);
    
    char* output = malloc(SHA256_DIGEST_LENGTH * 2 + 1);
    for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        sprintf(output + i * 2, "%02x", hash[i]);
    }
    output[SHA256_DIGEST_LENGTH * 2] = '\0';
    
    return output;
}


static int64_t time_now() {
    return (int64_t)time(NULL);
}

static char* time_format(int64_t timestamp, const char* format) {
    time_t t = (time_t)timestamp;
    struct tm* tm_info = localtime(&t);
    
    char* buffer = malloc(256);
    strftime(buffer, 256, format, tm_info);
    
    return buffer;
}

static int64_t time_parse(const char* time_str, const char* format) {
    struct tm tm_info = {0};
    
    if (strptime(time_str, format, &tm_info) == NULL) {
        return -1;
    }
    
    return (int64_t)mktime(&tm_info);
}

// PROCESS IMPLEMENTATION

static Process* process_spawn(const char* command, const char** args) {
    Process* proc = malloc(sizeof(Process));
    
    int stdin_pipe[2], stdout_pipe[2], stderr_pipe[2];
    pipe(stdin_pipe);
    pipe(stdout_pipe);
    pipe(stderr_pipe);
    
    proc->pid = fork();
    
    if (proc->pid == 0) {
        close(stdin_pipe[1]);
        close(stdout_pipe[0]);
        close(stderr_pipe[0]);
        
        dup2(stdin_pipe[0], STDIN_FILENO);
        dup2(stdout_pipe[1], STDOUT_FILENO);
        dup2(stderr_pipe[1], STDERR_FILENO);
        
        execvp(command, (char* const*)args);
        exit(1);
    }
    
    close(stdin_pipe[0]);
    close(stdout_pipe[1]);
    close(stderr_pipe[1]);
    
    proc->stdin_fd = stdin_pipe[1];
    proc->stdout_fd = stdout_pipe[0];
    proc->stderr_fd = stderr_pipe[0];
    
    return proc;
}

static int process_wait(Process* proc) {
    if (!proc) return -1;
    
    int status;
    waitpid(proc->pid, &status, 0);
    
    close(proc->stdin_fd);
    close(proc->stdout_fd);
    close(proc->stderr_fd);
    
    int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    free(proc);
    
    return exit_code;
}

static int process_kill(Process* proc, int signal) {
    if (!proc) return 0;
    return kill(proc->pid, signal) == 0;
}

static char* process_read(Process* proc) {
    if (!proc) return strdup("");
    
    // Use select() with timeout to wait for data
    fd_set readfds;
    struct timeval timeout;
    FD_ZERO(&readfds);
    FD_SET(proc->stdout_fd, &readfds);
    timeout.tv_sec = 0;
    timeout.tv_usec = 50000; // 50ms timeout
    
    int ready = select(proc->stdout_fd + 1, &readfds, NULL, NULL, &timeout);
    if (ready <= 0) {
        // Timeout or error - no data available
        return strdup("");
    }
    
    // Make stdout non-blocking for the read
    int flags = fcntl(proc->stdout_fd, F_GETFL, 0);
    fcntl(proc->stdout_fd, F_SETFL, flags | O_NONBLOCK);
    
    char buffer[4096];
    ssize_t n = read(proc->stdout_fd, buffer, sizeof(buffer) - 1);
    
    // Restore blocking mode
    fcntl(proc->stdout_fd, F_SETFL, flags);
    
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return strdup("");
        }
        return strdup("");
    }
    
    buffer[n] = '\0';
    return strdup(buffer);
}

static int process_write(Process* proc, const char* data) {
    if (!proc) return 0;
    
    ssize_t n = write(proc->stdin_fd, data, strlen(data));
    return n > 0;
}

// NETWORK SOCKET IMPLEMENTATION

static Socket* tcp_listen(int port) {
    Socket* sock = malloc(sizeof(Socket));
    sock->is_udp = false;
    
    sock->sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sock->sockfd < 0) {
        free(sock);
        return NULL;
    }
    
    int opt = 1;
    setsockopt(sock->sockfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    memset(&sock->addr, 0, sizeof(sock->addr));
    sock->addr.sin_family = AF_INET;
    sock->addr.sin_addr.s_addr = INADDR_ANY;
    sock->addr.sin_port = htons(port);
    
    if (bind(sock->sockfd, (struct sockaddr*)&sock->addr, sizeof(sock->addr)) < 0) {
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    if (listen(sock->sockfd, 10) < 0) {
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    return sock;
}

static Socket* tcp_accept(Socket* server_sock) {
    if (!server_sock) return NULL;
    
    Socket* client_sock = malloc(sizeof(Socket));
    client_sock->is_udp = false;
    client_sock->is_tls = false;
    client_sock->ssl = NULL;
    client_sock->ssl_ctx = NULL;
    
    socklen_t addr_len = sizeof(client_sock->addr);
    client_sock->sockfd = accept(server_sock->sockfd, 
        (struct sockaddr*)&client_sock->addr, &addr_len);
    
    if (client_sock->sockfd < 0) {
        free(client_sock);
        return NULL;
    }
    
    return client_sock;
}

static Socket* tcp_connect(const char* host, int port) {
    Socket* sock = malloc(sizeof(Socket));
    sock->is_udp = false;
    sock->is_tls = false;
    sock->ssl = NULL;
    sock->ssl_ctx = NULL;
    
    sock->sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sock->sockfd < 0) {
        free(sock);
        return NULL;
    }
    
    struct hostent* server = gethostbyname(host);
    if (!server) {
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    memset(&sock->addr, 0, sizeof(sock->addr));
    sock->addr.sin_family = AF_INET;
    memcpy(&sock->addr.sin_addr.s_addr, server->h_addr_list[0], server->h_length);
    sock->addr.sin_port = htons(port);
    
    if (connect(sock->sockfd, (struct sockaddr*)&sock->addr, sizeof(sock->addr)) < 0) {
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    return sock;
}

static Socket* tcp_tls_connect(const char* host, int port) {
    Socket* sock = tcp_connect(host, port);
    if (!sock) return NULL;
    
    sock->is_tls = true;
    sock->ssl_ctx = SSL_CTX_new(TLS_client_method());
    if (!sock->ssl_ctx) {
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    sock->ssl = SSL_new(sock->ssl_ctx);
    if (!sock->ssl) {
        SSL_CTX_free(sock->ssl_ctx);
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    if (SSL_set_fd(sock->ssl, sock->sockfd) != 1) {
        SSL_free(sock->ssl);
        SSL_CTX_free(sock->ssl_ctx);
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    if (SSL_connect(sock->ssl) != 1) {
        SSL_free(sock->ssl);
        SSL_CTX_free(sock->ssl_ctx);
        close(sock->sockfd);
        free(sock);
        return NULL;
    }
    
    return sock;
}

static int tcp_send(Socket* sock, const char* data) {
    if (!sock) return -1;
    if (sock->is_tls) {
        return SSL_write(sock->ssl, data, strlen(data));
    }
    return send(sock->sockfd, data, strlen(data), 0);
}

static char* tcp_receive(Socket* sock, int max_bytes) {
    if (!sock) return strdup("");
    
    char* buffer = malloc(max_bytes + 1);
    ssize_t n;
    
    if (sock->is_tls) {
        n = SSL_read(sock->ssl, buffer, max_bytes);
    } else {
        n = recv(sock->sockfd, buffer, max_bytes, 0);
    }
    
    if (n < 0) {
        free(buffer);
        return strdup("");
    }
    
    buffer[n] = '\0';
    return buffer;
}

static void tcp_close(Socket* sock) {
    if (!sock) return;
    if (sock->is_tls) {
        SSL_shutdown(sock->ssl);
        SSL_free(sock->ssl);
        SSL_CTX_free(sock->ssl_ctx);
    }
    close(sock->sockfd);
    free(sock);
}

static Socket* udp_socket() {
    Socket* sock = malloc(sizeof(Socket));
    sock->is_udp = true;
    sock->is_tls = false;
    sock->ssl = NULL;
    sock->ssl_ctx = NULL;
    
    sock->sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock->sockfd < 0) {
        free(sock);
        return NULL;
    }
    
    return sock;
}

static int udp_bind(Socket* sock, int port) {
    if (!sock || !sock->is_udp) return 0;
    
    memset(&sock->addr, 0, sizeof(sock->addr));
    sock->addr.sin_family = AF_INET;
    sock->addr.sin_addr.s_addr = INADDR_ANY;
    sock->addr.sin_port = htons(port);
    
    return bind(sock->sockfd, (struct sockaddr*)&sock->addr, sizeof(sock->addr)) >= 0;
}

// CHANNEL IMPLEMENTATION (Thread-Safe Queues)

static Channel* channel_new(int capacity) {
    Channel* ch = malloc(sizeof(Channel));
    ch->head = NULL;
    ch->tail = NULL;
    ch->capacity = capacity;
    ch->size = 0;
    pthread_mutex_init(&ch->mutex, NULL);
    pthread_cond_init(&ch->cond, NULL);
    return ch;
}

static void channel_send(Channel* ch, Value val) {
    pthread_mutex_lock(&ch->mutex);
    
    // Create new item
    ChannelItem* item = malloc(sizeof(ChannelItem));
    item->value = val;
    item->next = NULL;
    
    // Add to queue
    if (ch->tail) {
        ch->tail->next = item;
    } else {
        ch->head = item;
    }
    ch->tail = item;
    ch->size++;
    
    // Signal waiting receivers
    pthread_cond_signal(&ch->cond);
    pthread_mutex_unlock(&ch->mutex);
}

static Value channel_recv(Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    
    // Wait for data
    while (ch->size == 0) {
        pthread_cond_wait(&ch->cond, &ch->mutex);
    }
    
    // Remove from queue
    ChannelItem* item = ch->head;
    Value val = item->value;
    ch->head = item->next;
    if (!ch->head) {
        ch->tail = NULL;
    }
    ch->size--;
    free(item);
    
    pthread_mutex_unlock(&ch->mutex);
    return val;
}

VM* vm_new(BytecodeProgram* program) {
    VM* vm = malloc(sizeof(VM));
    if (!vm) {
        fprintf(stderr, "Failed to allocate VM struct\n");
        return NULL;
    }
    
    // Allocate stack dynamically
    vm->stack = malloc(STACK_SIZE * sizeof(Value));
    if (!vm->stack) {
        fprintf(stderr, "Failed to allocate VM stack (%zu bytes)\n", STACK_SIZE * sizeof(Value));
        free(vm);
        return NULL;
    }
    
    // Allocate call stack dynamically
    vm->call_stack = malloc(CALL_STACK_SIZE * sizeof(CallFrame));
    if (!vm->call_stack) {
        fprintf(stderr, "Failed to allocate VM call stack (%zu bytes)\n", CALL_STACK_SIZE * sizeof(CallFrame));
        free(vm->stack);
        free(vm);
        return NULL;
    }
    
    vm->program = program;
    vm->ip = 0;
    vm->sp = 0;
    vm->call_sp = 0;
    vm->stack_capacity = STACK_SIZE;
    vm->call_stack_capacity = CALL_STACK_SIZE;
    vm->running = true;
    vm->exit_code = 0;

    // Initialize globals (if needed)
    vm->global_count = 0;
    vm->globals = NULL;
    
    // Initialize garbage collector
    gc_init(&vm->gc);
    
    // Initialize FFI
    vm->ffi_libraries = NULL;

    return vm;
}

void vm_free(VM* vm) {
    // Free string values on stack
    for (uint32_t i = 0; i < vm->sp; i++) {
        if (vm->stack[i].type == VAL_STRING) {
            free(vm->stack[i].data.string_val);
        }
    }
    
    // Free FFI libraries
    FFILibrary* lib = vm->ffi_libraries;
    while (lib) {
        FFILibrary* next = lib->next;
        if (lib->handle) {
            dlclose(lib->handle);
        }
        free(lib->name);
        free(lib);
        lib = next;
    }
    
    // Free dynamic allocations
    free(vm->stack);
    free(vm->call_stack);
    free(vm->globals);
    free(vm);
}

// FFI (FOREIGN FUNCTION INTERFACE) OPERATIONS

// FFI search paths
static const char* ffi_get_home_extensions_path() {
    static char path[1024];
    const char* home = getenv("HOME");
    if (home) {
        snprintf(path, sizeof(path), "%s/.aisl/extensions", home);
        return path;
    }
    return NULL;
}

// Find library in search paths
static char* ffi_find_library(const char* lib_name) {
    static const char* search_paths[] = {
        "./extensions",
        NULL,  // Will be filled with ~/.aisl/extensions
        "/usr/lib/aisl/extensions",
        "/usr/local/lib/aisl/extensions"
    };
    
    // Add .so extension if not present
    char full_name[256];
    if (strstr(lib_name, ".so") == NULL) {
        snprintf(full_name, sizeof(full_name), "%s.so", lib_name);
    } else {
        snprintf(full_name, sizeof(full_name), "%s", lib_name);
    }
    
    // Try each search path
    for (int i = 0; i < 4; i++) {
        const char* base_path;
        if (i == 1) {
            base_path = ffi_get_home_extensions_path();
            if (!base_path) continue;
        } else {
            base_path = search_paths[i];
        }
        
        char full_path[1024];
        snprintf(full_path, sizeof(full_path), "%s/%s", base_path, full_name);
        
        // Check if file exists
        if (access(full_path, F_OK) == 0) {
            return strdup(full_path);
        }
    }
    
    return NULL;
}

// Load FFI library
static void* ffi_load_library(VM* vm, const char* lib_name) {
    // Check if already loaded
    FFILibrary* lib = vm->ffi_libraries;
    while (lib) {
        if (strcmp(lib->name, lib_name) == 0) {
            return lib->handle;
        }
        lib = lib->next;
    }
    
    // Find library file
    char* lib_path = ffi_find_library(lib_name);
    if (!lib_path) {
        fprintf(stderr, "Warning: FFI library '%s' not found in search paths:\n", lib_name);
        fprintf(stderr, "  - ./extensions\n");
        const char* home_path = ffi_get_home_extensions_path();
        if (home_path) {
            fprintf(stderr, "  - %s\n", home_path);
        }
        fprintf(stderr, "  - /usr/lib/aisl/extensions\n");
        fprintf(stderr, "  - /usr/local/lib/aisl/extensions\n");
        return NULL;
    }
    
    // Load library
    void* handle = dlopen(lib_path, RTLD_LAZY);
    if (!handle) {
        fprintf(stderr, "Warning: Failed to load FFI library '%s': %s\n", lib_path, dlerror());
        free(lib_path);
        return NULL;
    }
    
    // Add to loaded libraries list
    FFILibrary* new_lib = malloc(sizeof(FFILibrary));
    new_lib->name = strdup(lib_name);
    new_lib->handle = handle;
    new_lib->next = vm->ffi_libraries;
    vm->ffi_libraries = new_lib;
    
    free(lib_path);
    return handle;
}

// Check if FFI library is available
static bool ffi_is_available(const char* lib_name) {
    char* lib_path = ffi_find_library(lib_name);
    if (lib_path) {
        free(lib_path);
        return true;
    }
    return false;
}

// Close FFI library (handle must be valid)
static void ffi_close_library(VM* vm, void* handle) {
    FFILibrary* prev = NULL;
    FFILibrary* lib = vm->ffi_libraries;
    
    while (lib) {
        if (lib->handle == handle) {
            // Remove from list
            if (prev) {
                prev->next = lib->next;
            } else {
                vm->ffi_libraries = lib->next;
            }
            
            // Close and free
            if (lib->handle) {
                dlclose(lib->handle);
            }
            free(lib->name);
            free(lib);
            return;
        }
        prev = lib;
        lib = lib->next;
    }
}

// STACK OPERATIONS

static inline void push(VM* vm, Value val) {
    if (vm->sp >= STACK_SIZE) {
        fprintf(stderr, "Stack overflow\n");
        exit(1);
    }
    vm->stack[vm->sp++] = val;
}

static inline Value pop(VM* vm) {
    if (vm->sp == 0) {
        fprintf(stderr, "Stack underflow\n");
        exit(1);
    }
    return vm->stack[--vm->sp];
}

static inline Value peek(VM* vm, uint32_t offset) {
    if (vm->sp <= offset) {
        fprintf(stderr, "Stack underflow on peek\n");
        exit(1);
    }
    return vm->stack[vm->sp - 1 - offset];
}

// VM EXECUTION

int vm_run(VM* vm) {
    // Find main function
    uint32_t main_idx = (uint32_t)-1;
    for (uint32_t i = 0; i < vm->program->function_count; i++) {
        if (strcmp(vm->program->functions[i].name, "main") == 0) {
            main_idx = i;
            break;
        }
    }

    if (main_idx == (uint32_t)-1) {
        fprintf(stderr, "Error: No 'main' function found. Entry point must be named 'main'.\n");
        return 1;
    }

    vm->ip = vm->program->functions[main_idx].start_addr;

    vm->call_sp = 1;
    vm->call_stack[0].return_addr = vm->program->instruction_count;
    vm->call_stack[0].frame_pointer = 0;
    vm->call_stack[0].local_count = vm->program->functions[main_idx].local_count;

    for (uint32_t i = 0; i < vm->program->functions[main_idx].local_count; i++) {
        Value unit = {.type = VAL_UNIT};
        push(vm, unit);
    }

    while (vm->running && vm->ip < vm->program->instruction_count) {
        Instruction inst = vm->program->instructions[vm->ip];

        switch (inst.opcode) {
            case OP_PUSH_INT: {
                Value val = {.type = VAL_INT, .data.int_val = inst.operand.int_val};
                push(vm, val);
                vm->ip++;
                break;
            }

            case OP_PUSH_STRING: {
                uint32_t str_idx = inst.operand.uint_val;
                Value val = {
                    .type = VAL_STRING,
                    .data.string_val = strdup(vm->program->string_constants[str_idx])
                };
                push(vm, val);
                vm->ip++;
                break;
            }

        case OP_PUSH_BOOL: {
            Value val = {.type = VAL_BOOL, .data.bool_val = inst.operand.bool_val};
            push(vm, val);
            vm->ip++;
            break;
            }

            case OP_PUSH_UNIT: {
                Value val = {.type = VAL_UNIT};
                push(vm, val);
                vm->ip++;
                break;
            }


            
            case OP_PUSH_FLOAT: {
                Value val = {.type = VAL_F64, .data.f64_val = inst.operand.float_val};
                push(vm, val);
                vm->ip++;
                break;
            }

            case OP_PUSH_DECIMAL: {
                uint32_t str_idx = inst.operand.uint_val;
                Value val = {
                    .type = VAL_DECIMAL,
                    .data.decimal_val = strdup(vm->program->string_constants[str_idx])
                };
                push(vm, val);
                vm->ip++;
                break;
            }

            case OP_POP: {
                Value val = pop(vm);
                if (val.type == VAL_STRING) {
                    free(val.data.string_val);
                }
                if (val.type == VAL_DECIMAL) {
                    free(val.data.decimal_val);
                }
                vm->ip++;
                break;
            }

            case OP_DUP: {
                Value val = peek(vm, 0);
                push(vm, value_clone(val));
                vm->ip++;
                break;
            }

            case OP_LOAD_LOCAL: {
                uint32_t idx = inst.operand.uint_val;
                uint32_t fp = vm->call_stack[vm->call_sp - 1].frame_pointer;
                Value val = vm->stack[fp + idx];
                Value cloned = value_clone(val);
                push(vm, cloned);
                vm->ip++;
                break;
            }

            case OP_STORE_LOCAL: {
                uint32_t idx = inst.operand.uint_val;
                uint32_t fp = vm->call_stack[vm->call_sp - 1].frame_pointer;
                Value val = pop(vm);
                if (vm->stack[fp + idx].type == VAL_STRING) {
                    free(vm->stack[fp + idx].data.string_val);
                }
                if (vm->stack[fp + idx].type == VAL_DECIMAL) {
                    free(vm->stack[fp + idx].data.decimal_val);
                }
                vm->stack[fp + idx] = val;
                vm->ip++;
                break;
            }

            // INT (I64) ARITHMETIC (v6.0 - removed i32)

            case OP_ADD_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_I64, .data.i64_val = a.data.i64_val + b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_SUB_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_I64, .data.i64_val = a.data.i64_val - b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MUL_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_I64, .data.i64_val = a.data.i64_val * b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_DIV_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                if (b.data.i64_val == 0) {
                    fprintf(stderr, "Division by zero\n");
                    return 1;
                }
                Value result = {.type = VAL_I64, .data.i64_val = a.data.i64_val / b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MOD_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                if (b.data.i64_val == 0) {
                    fprintf(stderr, "Modulo by zero\n");
                    return 1;
                }
                Value result = {.type = VAL_I64, .data.i64_val = a.data.i64_val % b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NEG_I64: {
                Value a = pop(vm);
                Value result = {.type = VAL_I64, .data.i64_val = -a.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            // TYPED F32 ARITHMETIC

            // FLOAT (F64) ARITHMETIC - AISL 'float' type

            case OP_ADD_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_F64, .data.f64_val = a.data.f64_val + b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_SUB_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_F64, .data.f64_val = a.data.f64_val - b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MUL_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_F64, .data.f64_val = a.data.f64_val * b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_DIV_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_F64, .data.f64_val = a.data.f64_val / b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NEG_F64: {
                Value a = pop(vm);
                Value result = {.type = VAL_F64, .data.f64_val = -a.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            // DECIMAL ARITHMETIC

            case OP_ADD_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                char* result_str = decimal_add(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = result_str};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_SUB_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                char* result_str = decimal_sub(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = result_str};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MUL_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                char* result_str = decimal_mul(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = result_str};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_DIV_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                char* result_str = decimal_div(a.data.decimal_val, b.data.decimal_val, 15);  // 15 digit precision
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = result_str};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NEG_DECIMAL: {
                Value a = pop(vm);
                char* result_str = decimal_neg(a.data.decimal_val);
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = result_str};
                free(a.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            // INT (I64) COMPARISONS (v6.0 - removed i32)

            case OP_EQ_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.i64_val == b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NE_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.i64_val != b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_LT_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.i64_val < b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_GT_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.i64_val > b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_LE_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.i64_val <= b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_GE_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.i64_val >= b.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            // FLOAT (F64) COMPARISONS - AISL 'float' type

            case OP_EQ_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.f64_val == b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NE_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.f64_val != b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_LT_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.f64_val < b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_GT_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.f64_val > b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_LE_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.f64_val <= b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_GE_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.f64_val >= b.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            // DECIMAL COMPARISONS

            case OP_EQ_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                int cmp = decimal_cmp(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = (cmp == 0)};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NE_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                int cmp = decimal_cmp(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = (cmp != 0)};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_LT_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                int cmp = decimal_cmp(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = (cmp < 0)};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_GT_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                int cmp = decimal_cmp(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = (cmp > 0)};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_LE_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                int cmp = decimal_cmp(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = (cmp <= 0)};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_GE_DECIMAL: {
                Value b = pop(vm);
                Value a = pop(vm);
                int cmp = decimal_cmp(a.data.decimal_val, b.data.decimal_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = (cmp >= 0)};
                free(a.data.decimal_val);
                free(b.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            // String comparison
            case OP_EQ_STR: {
                Value b = pop(vm);
                Value a = pop(vm);
                bool eq = strcmp(a.data.string_val, b.data.string_val) == 0;
                Value result = {.type = VAL_BOOL, .data.bool_val = eq};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NE_STR: {
                Value b = pop(vm);
                Value a = pop(vm);
                bool ne = strcmp(a.data.string_val, b.data.string_val) != 0;
                Value result = {.type = VAL_BOOL, .data.bool_val = ne};
                push(vm, result);
                vm->ip++;
                break;
            }

            // Boolean comparison
            case OP_EQ_BOOL: {
                Value b = pop(vm);
                Value a = pop(vm);
                bool eq = a.data.bool_val == b.data.bool_val;
                Value result = {.type = VAL_BOOL, .data.bool_val = eq};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NE_BOOL: {
                Value b = pop(vm);
                Value a = pop(vm);
                bool ne = a.data.bool_val != b.data.bool_val;
                Value result = {.type = VAL_BOOL, .data.bool_val = ne};
                push(vm, result);
                vm->ip++;
                break;
            }

            // Explicit boolean logical operations
            case OP_AND_BOOL: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.bool_val && b.data.bool_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_OR_BOOL: {
                Value b = pop(vm);
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = a.data.bool_val || b.data.bool_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_NOT_BOOL: {
                Value a = pop(vm);
                Value result = {.type = VAL_BOOL, .data.bool_val = !a.data.bool_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            // Control flow
            case OP_JUMP: {
                vm->ip = inst.operand.jump.target;
                break;
            }

            case OP_JUMP_IF_FALSE: {
                Value cond = pop(vm);
                if (!cond.data.bool_val) {
                    vm->ip = inst.operand.jump.target;
                } else {
                    vm->ip++;
                }
                break;
            }

            case OP_JUMP_IF_TRUE: {
                Value cond = pop(vm);
                if (cond.data.bool_val) {
                    vm->ip = inst.operand.jump.target;
                } else {
                    vm->ip++;
                }
                break;
            }

            case OP_CALL: {
                uint32_t func_idx = inst.operand.call.func_idx;
                uint32_t arg_count = inst.operand.call.arg_count;

                if (vm->call_sp >= vm->call_stack_capacity) {
                    fprintf(stderr, "Call stack overflow\n");
                    return 1;
                }
                if (vm->sp < arg_count) {
                    fprintf(stderr, "Stack underflow on call\n");
                    return 1;
                }

                uint32_t fp = vm->sp - arg_count;
                uint32_t local_count = vm->program->functions[func_idx].local_count;
                uint32_t param_count = vm->program->functions[func_idx].param_count;
                
                CallFrame frame = {
                    .return_addr = vm->ip + 1,
                    .frame_pointer = fp,
                    .local_count = local_count,
                    .param_count = param_count
                };
                vm->call_stack[vm->call_sp++] = frame;

                // Initialize locals AFTER parameters (locals start at fp + arg_count)
                uint32_t target_sp = fp + local_count;
                while (vm->sp < target_sp) {
                    Value unit = {.type = VAL_UNIT};
                    push(vm, unit);
                }

                vm->ip = vm->program->functions[func_idx].start_addr;
                break;
            }

            case OP_RETURN: {
                if (vm->call_sp == 0) {
                    vm->running = false;
                    break;
                }

                Value ret = pop(vm);
                CallFrame frame = vm->call_stack[--vm->call_sp];
                
                // Free ONLY non-parameter locals (locals[param_count:])
                // Parameters are owned by the caller and will be freed when caller returns
                uint32_t fp = frame.frame_pointer;
                uint32_t local_count = frame.local_count;
                uint32_t param_count = frame.param_count;
                for (uint32_t i = param_count; i < local_count; i++) {
                    if (vm->stack[fp + i].type == VAL_STRING && vm->stack[fp + i].data.string_val != NULL) {
                        free(vm->stack[fp + i].data.string_val);
                        vm->stack[fp + i].data.string_val = NULL;
                    }
                }
                
                vm->sp = frame.frame_pointer;

                if (vm->call_sp == 0) {
                    push(vm, ret);
                    vm->running = false;
                } else {
                    push(vm, ret);
                    vm->ip = frame.return_addr;
                }
                break;
            }

            // I/O
            case OP_IO_WRITE: {
                Value data = pop(vm);
                Value handle = pop(vm);

                if (data.type == VAL_STRING) {
                    write((int)handle.data.int_val, data.data.string_val, strlen(data.data.string_val));
                    free(data.data.string_val);
                }

                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_IO_READ: {
                Value handle = pop(vm);
                char buffer[4096];
                ssize_t n = read((int)handle.data.int_val, buffer, sizeof(buffer) - 1);
                if (n > 0) {
                    buffer[n] = '\0';
                    Value result = {.type = VAL_STRING, .data.string_val = strdup(buffer)};
                    push(vm, result);
                } else {
                    Value result = {.type = VAL_STRING, .data.string_val = strdup("")};
                    push(vm, result);
                }
                vm->ip++;
                break;
            }

            case OP_IO_OPEN: {
                Value mode = pop(vm);
                Value path = pop(vm);
                int flags = O_RDONLY;
                if (mode.data.int_val == 1) {
                    flags = O_WRONLY | O_CREAT | O_TRUNC;
                } else if (mode.data.int_val == 2) {
                    flags = O_WRONLY | O_CREAT | O_APPEND;
                } else if (mode.data.int_val == 3) {
                    flags = O_RDWR | O_CREAT;
                }

                int fd = open(path.data.string_val, flags, 0644);
                free(path.data.string_val);
                Value result = {.type = VAL_INT, .data.int_val = fd};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_IO_CLOSE: {
                Value handle = pop(vm);
                close((int)handle.data.int_val);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_STDIN_READ: {
                char line[4096];
                if (fgets(line, sizeof(line), stdin) != NULL) {
                    size_t len = strlen(line);
                    if (len > 0 && line[len-1] == '\n') {
                        line[len-1] = '\0';
                    }
                    char* result = strdup(line);
                    Value result_val = {.type = VAL_STRING, .data.string_val = result};
                    push(vm, result_val);
                } else {
                    Value empty = {.type = VAL_STRING, .data.string_val = strdup("")};
                    push(vm, empty);
                }
                vm->ip++;
                break;
            }

            case OP_STDIN_READ_ALL: {
                char buffer[65536];
                size_t total = 0;
                while (fgets(buffer + total, sizeof(buffer) - total, stdin) != NULL) {
                    total += strlen(buffer + total);
                    if (total >= sizeof(buffer) - 1) break;
                }
                char* result = strdup(buffer);
                Value result_val = {.type = VAL_STRING, .data.string_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_STR_LEN: {
                Value str = pop(vm);
                int64_t len = (int64_t)strlen(str.data.string_val);
                free(str.data.string_val);
                Value result = {.type = VAL_INT, .data.int_val = len};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_CONCAT: {
                Value b = pop(vm);
                Value a = pop(vm);
                size_t len_a = strlen(a.data.string_val);
                size_t len_b = strlen(b.data.string_val);
                char* joined = malloc(len_a + len_b + 1);
                memcpy(joined, a.data.string_val, len_a);
                memcpy(joined + len_a, b.data.string_val, len_b);
                joined[len_a + len_b] = '\0';
                free(a.data.string_val);
                free(b.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = joined};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_SLICE: {
                Value len_val = pop(vm);
                Value start_val = pop(vm);
                Value str = pop(vm);
                int64_t start = start_val.data.int_val;
                int64_t len = len_val.data.int_val;
                size_t str_len = strlen(str.data.string_val);

                if (start < 0) start = 0;
                if (len < 0) len = 0;
                if ((size_t)start > str_len) start = (int64_t)str_len;
                if ((size_t)(start + len) > str_len) {
                    len = (int64_t)(str_len - start);
                }

                char* slice = malloc((size_t)len + 1);
                memcpy(slice, str.data.string_val + start, (size_t)len);
                slice[len] = '\0';
                free(str.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = slice};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_GET: {
                Value idx_val = pop(vm);
                Value str = pop(vm);
                int64_t idx = idx_val.data.int_val;
                int64_t code = -1;
                size_t str_len = strlen(str.data.string_val);
                if (idx >= 0 && (size_t)idx < str_len) {
                    code = (unsigned char)str.data.string_val[idx];
                }
                free(str.data.string_val);
                Value result = {.type = VAL_INT, .data.int_val = code};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_FROM_I64: {
                Value val = pop(vm);
                char buffer[32];
                snprintf(buffer, sizeof(buffer), "%lld", (long long)val.data.int_val);
                Value result = {.type = VAL_STRING, .data.string_val = strdup(buffer)};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_FROM_F64: {
                Value val = pop(vm);
                char buffer[64];
                snprintf(buffer, sizeof(buffer), "%g", val.data.f64_val);
                Value result = {.type = VAL_STRING, .data.string_val = strdup(buffer)};
                push(vm, result);
                vm->ip++;
                break;
            }

            // String operations (OP_STR_SPLIT, OP_STR_TRIM, etc.) REMOVED
            // Now implemented in stdlib/core/string_utils.aisl

            case OP_ARRAY_NEW: {
                Value cap_val = pop(vm);
                int64_t cap = cap_val.data.int_val;
                if (cap < 1) cap = 1;
                Array* arr = malloc(sizeof(Array));
                arr->count = 0;
                arr->capacity = (uint32_t)cap;
                arr->items = malloc(sizeof(Value) * arr->capacity);
                Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_ARRAY_PUSH: {
                Value val = pop(vm);
                Value arr_val = pop(vm);
                Array* arr = (Array*)arr_val.data.ptr_val;
                if (arr->count >= arr->capacity) {
                    arr->capacity *= 2;
                    arr->items = realloc(arr->items, sizeof(Value) * arr->capacity);
                }
                arr->items[arr->count++] = val;
                push(vm, arr_val);
                vm->ip++;
                break;
            }

            case OP_ARRAY_GET: {
                Value idx_val = pop(vm);
                Value arr_val = pop(vm);
                Array* arr = (Array*)arr_val.data.ptr_val;
                int64_t idx = idx_val.data.int_val;
                if (idx < 0 || (uint32_t)idx >= arr->count) {
                    Value unit = {.type = VAL_UNIT};
                    push(vm, unit);
                } else {
                    push(vm, value_clone(arr->items[idx]));
                }
                vm->ip++;
                break;
            }

            case OP_ARRAY_SET: {
                Value val = pop(vm);
                Value idx_val = pop(vm);
                Value arr_val = pop(vm);
                Array* arr = (Array*)arr_val.data.ptr_val;
                int64_t idx = idx_val.data.int_val;
                if (idx >= 0 && (uint32_t)idx < arr->count) {
                    arr->items[idx] = val;
                }
                push(vm, arr_val);
                vm->ip++;
                break;
            }

            case OP_ARRAY_LEN: {
                Value arr_val = pop(vm);
                Array* arr = (Array*)arr_val.data.ptr_val;
                Value result = {.type = VAL_INT, .data.int_val = (int64_t)arr->count};
                push(vm, result);
                vm->ip++;
                break;
            }

            // MAP OPERATIONS

            case OP_MAP_NEW: {
                Map* map = malloc(sizeof(Map));
                map->bucket_count = 16;  // Initial bucket count
                map->size = 0;
                map->buckets = calloc(map->bucket_count, sizeof(MapEntry*));
                Value result = {.type = VAL_MAP, .data.ptr_val = map};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MAP_SET: {
                Value val = pop(vm);
                Value key_val = pop(vm);
                Value map_val = pop(vm);
                Map* map = (Map*)map_val.data.ptr_val;
                
                // Convert key to string
                char* key;
                if (key_val.type == VAL_STRING) {
                    key = key_val.data.string_val;
                } else if (key_val.type == VAL_I32) {
                    key = malloc(32);
                    snprintf(key, 32, "%d", key_val.data.i32_val);
                } else if (key_val.type == VAL_I64 || key_val.type == VAL_INT) {
                    key = malloc(32);
                    snprintf(key, 32, "%lld", (long long)key_val.data.i64_val);
                } else {
                    // Unsupported key type, push map back unchanged
                    push(vm, map_val);
                    vm->ip++;
                    break;
                }
                
                uint32_t bucket_idx = hash_string(key, map->bucket_count);
                MapEntry* entry = map->buckets[bucket_idx];
                
                // Check if key already exists
                while (entry != NULL) {
                    if (strcmp(entry->key, key) == 0) {
                        // Update existing value
                        entry->value = val;
                        if (key_val.type != VAL_STRING) free(key);
                        push(vm, map_val);
                        vm->ip++;
                        break;
                    }
                    entry = entry->next;
                }
                
                // Key doesn't exist, create new entry
                if (entry == NULL) {
                    MapEntry* new_entry = malloc(sizeof(MapEntry));
                    if (key_val.type == VAL_STRING) {
                        new_entry->key = strdup(key);
                    } else {
                        new_entry->key = key;
                    }
                    new_entry->value = val;
                    new_entry->next = map->buckets[bucket_idx];
                    map->buckets[bucket_idx] = new_entry;
                    map->size++;
                    push(vm, map_val);
                    vm->ip++;
                }
                break;
            }

            case OP_MAP_GET: {
                Value key_val = pop(vm);
                Value map_val = pop(vm);
                Map* map = (Map*)map_val.data.ptr_val;
                
                // Convert key to string
                char* key;
                bool free_key = false;
                if (key_val.type == VAL_STRING) {
                    key = key_val.data.string_val;
                } else if (key_val.type == VAL_I32) {
                    key = malloc(32);
                    snprintf(key, 32, "%d", key_val.data.i32_val);
                    free_key = true;
                } else if (key_val.type == VAL_I64 || key_val.type == VAL_INT) {
                    key = malloc(32);
                    snprintf(key, 32, "%lld", (long long)key_val.data.i64_val);
                    free_key = true;
                } else {
                    // Unsupported key type, return unit
                    Value unit = {.type = VAL_UNIT};
                    push(vm, unit);
                    vm->ip++;
                    break;
                }
                
                uint32_t bucket_idx = hash_string(key, map->bucket_count);
                MapEntry* entry = map->buckets[bucket_idx];
                
                // Search for key
                while (entry != NULL) {
                    if (strcmp(entry->key, key) == 0) {
                        push(vm, value_clone(entry->value));
                        if (free_key) free(key);
                        vm->ip++;
                        break;
                    }
                    entry = entry->next;
                }
                
                // Key not found
                if (entry == NULL) {
                    if (free_key) free(key);
                    Value unit = {.type = VAL_UNIT};
                    push(vm, unit);
                    vm->ip++;
                }
                break;
            }

            case OP_MAP_HAS: {
                Value key_val = pop(vm);
                Value map_val = pop(vm);
                Map* map = (Map*)map_val.data.ptr_val;
                
                // Convert key to string
                char* key;
                bool free_key = false;
                if (key_val.type == VAL_STRING) {
                    key = key_val.data.string_val;
                } else if (key_val.type == VAL_I32) {
                    key = malloc(32);
                    snprintf(key, 32, "%d", key_val.data.i32_val);
                    free_key = true;
                } else if (key_val.type == VAL_I64 || key_val.type == VAL_INT) {
                    key = malloc(32);
                    snprintf(key, 32, "%lld", (long long)key_val.data.i64_val);
                    free_key = true;
                } else {
                    // Unsupported key type, return false
                    Value result = {.type = VAL_BOOL, .data.bool_val = false};
                    push(vm, result);
                    vm->ip++;
                    break;
                }
                
                uint32_t bucket_idx = hash_string(key, map->bucket_count);
                MapEntry* entry = map->buckets[bucket_idx];
                
                // Search for key
                bool found = false;
                while (entry != NULL) {
                    if (strcmp(entry->key, key) == 0) {
                        found = true;
                        break;
                    }
                    entry = entry->next;
                }
                
                if (free_key) free(key);
                Value result = {.type = VAL_BOOL, .data.bool_val = found};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MAP_DELETE: {
                Value key_val = pop(vm);
                Value map_val = pop(vm);
                Map* map = (Map*)map_val.data.ptr_val;
                
                // Convert key to string
                char* key;
                bool free_key = false;
                if (key_val.type == VAL_STRING) {
                    key = key_val.data.string_val;
                } else if (key_val.type == VAL_I32) {
                    key = malloc(32);
                    snprintf(key, 32, "%d", key_val.data.i32_val);
                    free_key = true;
                } else if (key_val.type == VAL_I64 || key_val.type == VAL_INT) {
                    key = malloc(32);
                    snprintf(key, 32, "%lld", (long long)key_val.data.i64_val);
                    free_key = true;
                } else {
                    // Unsupported key type, push map back unchanged
                    push(vm, map_val);
                    vm->ip++;
                    break;
                }
                
                uint32_t bucket_idx = hash_string(key, map->bucket_count);
                MapEntry* entry = map->buckets[bucket_idx];
                MapEntry* prev = NULL;
                
                // Search for key
                while (entry != NULL) {
                    if (strcmp(entry->key, key) == 0) {
                        // Found it, remove from chain
                        if (prev == NULL) {
                            map->buckets[bucket_idx] = entry->next;
                        } else {
                            prev->next = entry->next;
                        }
                        free(entry->key);
                        free(entry);
                        map->size--;
                        break;
                    }
                    prev = entry;
                    entry = entry->next;
                }
                
                if (free_key) free(key);
                push(vm, map_val);
                vm->ip++;
                break;
            }

            case OP_MAP_LEN: {
                Value map_val = pop(vm);
                Map* map = (Map*)map_val.data.ptr_val;
                Value result = {.type = VAL_INT, .data.int_val = (int64_t)map->size};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_MAP_KEYS: {
                Value map_val = pop(vm);
                Map* map = (Map*)map_val.data.ptr_val;
                
                // Create array to hold keys
                Array* keys_array = malloc(sizeof(Array));
                keys_array->capacity = map->size > 0 ? map->size : 1;
                keys_array->count = 0;
                keys_array->items = malloc(sizeof(Value) * keys_array->capacity);
                
                // Iterate through map buckets and collect keys
                for (uint32_t i = 0; i < map->bucket_count; i++) {
                    MapEntry* entry = map->buckets[i];
                    while (entry != NULL) {
                        Value key_val = {.type = VAL_STRING, .data.string_val = strdup(entry->key)};
                        keys_array->items[keys_array->count++] = key_val;
                        entry = entry->next;
                    }
                }
                
                Value result = {.type = VAL_ARRAY, .data.ptr_val = keys_array};
                push(vm, result);
                vm->ip++;
                break;
            }

            // JSON OPERATIONS

            // JSON operations (OP_JSON_PARSE, OP_JSON_STRINGIFY, etc.) REMOVED
            // Now implemented in stdlib/data/json.aisl using map primitives

            // HTTP OPERATIONS

            // HTTP operations (OP_HTTP_GET, OP_HTTP_POST, etc.) REMOVED
            // Now implemented in stdlib/net/http.aisl using TCP/TLS primitives

            // FILE OPERATIONS

            case OP_FILE_READ: {
                Value path_val = pop(vm);
                char* content = file_read(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = content ? content : strdup("")};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_FILE_WRITE: {
                Value content_val = pop(vm);
                Value path_val = pop(vm);
                int success = file_write(path_val.data.string_val, content_val.data.string_val);
                free(path_val.data.string_val);
                free(content_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = success};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_FILE_APPEND: {
                Value content_val = pop(vm);
                Value path_val = pop(vm);
                int success = file_append(path_val.data.string_val, content_val.data.string_val);
                free(path_val.data.string_val);
                free(content_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = success};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_FILE_EXISTS: {
                Value path_val = pop(vm);
                int exists = file_exists(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = exists};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_FILE_DELETE: {
                Value path_val = pop(vm);
                int success = file_delete(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = success};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_FILE_SIZE: {
                Value path_val = pop(vm);
                int64_t size = file_size(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_I64, .data.i64_val = size};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_FILE_MTIME: {
                Value path_val = pop(vm);
                int64_t mtime = file_mtime(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_I64, .data.i64_val = mtime};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_DIR_LIST: {
                Value path_val = pop(vm);
                Array* arr = dir_list(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_DIR_CREATE: {
                Value path_val = pop(vm);
                int success = dir_create(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = success};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_DIR_DELETE: {
                Value path_val = pop(vm);
                int success = dir_delete(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = success};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_REGEX_COMPILE: {
                Value pattern_val = pop(vm);
                RegexValue* re = regex_compile(pattern_val.data.string_val);
                free(pattern_val.data.string_val);
                Value result = {.type = VAL_REGEX, .data.ptr_val = re};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_REGEX_MATCH: {
                Value text_val = pop(vm);
                Value regex_val = pop(vm);
                RegexValue* re = (RegexValue*)regex_val.data.ptr_val;
                int match = regex_match(re, text_val.data.string_val);
                free(text_val.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = match};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_REGEX_FIND: {
                Value text_val = pop(vm);
                Value regex_val = pop(vm);
                RegexValue* re = (RegexValue*)regex_val.data.ptr_val;
                char* found = regex_find(re, text_val.data.string_val);
                free(text_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = found};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_REGEX_FIND_ALL: {
                Value text_val = pop(vm);
                Value regex_val = pop(vm);
                RegexValue* re = (RegexValue*)regex_val.data.ptr_val;
                Array* arr = regex_find_all(re, text_val.data.string_val);
                free(text_val.data.string_val);
                Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_REGEX_REPLACE: {
                Value replacement_val = pop(vm);
                Value text_val = pop(vm);
                Value regex_val = pop(vm);
                RegexValue* re = (RegexValue*)regex_val.data.ptr_val;
                char* replaced = regex_replace(re, text_val.data.string_val, replacement_val.data.string_val);
                free(text_val.data.string_val);
                free(replacement_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = replaced};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CRYPTO_SHA256: {
                Value input_val = pop(vm);
                char* hash = crypto_sha256(input_val.data.string_val);
                free(input_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = hash};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CRYPTO_MD5: {
                Value input_val = pop(vm);
                char* hash = crypto_md5(input_val.data.string_val);
                free(input_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = hash};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CRYPTO_HMAC_SHA256: {
                Value message_val = pop(vm);
                Value key_val = pop(vm);
                char* hash = crypto_hmac_sha256(key_val.data.string_val, message_val.data.string_val);
                free(key_val.data.string_val);
                free(message_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = hash};
                push(vm, result);
                vm->ip++;
                break;
            }

            // Base64 operations (OP_BASE64_ENCODE, OP_BASE64_DECODE) REMOVED
            // Now implemented in stdlib/data/base64.aisl using pure AISL

            case OP_TIME_NOW: {
                int64_t now = time_now();
                Value result = {.type = VAL_I64, .data.i64_val = now};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TIME_FORMAT: {
                Value format_val = pop(vm);
                Value timestamp_val = pop(vm);
                char* formatted = time_format(timestamp_val.data.i64_val, format_val.data.string_val);
                free(format_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = formatted};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TIME_PARSE: {
                Value format_val = pop(vm);
                Value time_str_val = pop(vm);
                int64_t timestamp = time_parse(time_str_val.data.string_val, format_val.data.string_val);
                free(time_str_val.data.string_val);
                free(format_val.data.string_val);
                Value result = {.type = VAL_I64, .data.i64_val = timestamp};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_PRINT_I64: {
                Value val = pop(vm);
                printf("%ld", val.data.i64_val);
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_PRINT_F64: {
                Value val = pop(vm);
                printf("%.15f", val.data.f64_val);
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_PRINT_STR: {
                Value val = pop(vm);
                if (val.type == VAL_STRING) {
                    printf("%s", val.data.string_val);
                } else {
                    printf("[non-string]");
                }
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_PRINT_BOOL: {
                Value val = pop(vm);
                printf("%s", val.data.bool_val ? "true" : "false");
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_PRINT_DECIMAL: {
                Value val = pop(vm);
                if (val.type == VAL_DECIMAL) {
                    printf("%s", val.data.decimal_val);
                    free(val.data.decimal_val);
                } else {
                    printf("[non-decimal]");
                }
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_PRINT_ARRAY: {
                Value val = pop(vm);
                if (val.type == VAL_ARRAY) {
                    Array* arr = (Array*)val.data.ptr_val;
                    printf("[");
                    for (uint32_t i = 0; i < arr->count; i++) {
                        if (i > 0) printf(", ");
                        Value item = arr->items[i];
                        switch (item.type) {
                            case VAL_I32: printf("%d", item.data.i32_val); break;
                            case VAL_I64: printf("%ld", item.data.i64_val); break;
                            case VAL_F32: printf("%.6f", item.data.f32_val); break;
                            case VAL_F64: printf("%.15f", item.data.f64_val); break;
                            case VAL_BOOL: printf("%s", item.data.bool_val ? "true" : "false"); break;
                            case VAL_STRING: printf("\"%s\"", item.data.string_val); break;
                            case VAL_DECIMAL: printf("%s", item.data.decimal_val); break;
                            default: printf("?"); break;
                        }
                    }
                    printf("]");
                } else {
                    printf("[non-array]");
                }
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_PRINT_MAP: {
                Value val = pop(vm);
                if (val.type == VAL_MAP) {
                    Map* map = (Map*)val.data.ptr_val;
                    printf("{");
                    bool first = true;
                    for (uint32_t i = 0; i < map->bucket_count; i++) {
                        MapEntry* entry = map->buckets[i];
                        while (entry) {
                            if (!first) printf(", ");
                            first = false;
                            printf("\"%s\": ", entry->key);
                            Value item = entry->value;
                            switch (item.type) {
                                case VAL_I32: printf("%d", item.data.i32_val); break;
                                case VAL_I64: printf("%ld", item.data.i64_val); break;
                                case VAL_F32: printf("%.6f", item.data.f32_val); break;
                                case VAL_F64: printf("%.15f", item.data.f64_val); break;
                                case VAL_BOOL: printf("%s", item.data.bool_val ? "true" : "false"); break;
                                case VAL_STRING: printf("\"%s\"", item.data.string_val); break;
                                default: printf("?"); break;
                            }
                            entry = entry->next;
                        }
                    }
                    printf("}");
                } else {
                    printf("[non-map]");
                }
                fflush(stdout);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            // TYPE CONVERSION OPERATIONS (v6.0 - int/float only)

            case OP_CAST_I64_F64: {
                Value val = pop(vm);
                Value result = {.type = VAL_F64, .data.f64_val = (double)val.data.i64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CAST_F64_I64: {
                Value val = pop(vm);
                Value result = {.type = VAL_I64, .data.i64_val = (int64_t)val.data.f64_val};
                push(vm, result);
                vm->ip++;
                break;
            }

            // DECIMAL CONVERSIONS

            case OP_CAST_INT_DECIMAL: {
                Value val = pop(vm);
                char* decimal_str = decimal_from_int(val.data.i64_val);
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = decimal_str};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CAST_DECIMAL_INT: {
                Value val = pop(vm);
                int64_t int_val = decimal_to_int(val.data.decimal_val);
                Value result = {.type = VAL_I64, .data.i64_val = int_val};
                free(val.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CAST_FLOAT_DECIMAL: {
                Value val = pop(vm);
                char* decimal_str = decimal_from_float(val.data.f64_val);
                Value result = {.type = VAL_DECIMAL, .data.decimal_val = decimal_str};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CAST_DECIMAL_FLOAT: {
                Value val = pop(vm);
                double float_val = decimal_to_float(val.data.decimal_val);
                Value result = {.type = VAL_F64, .data.f64_val = float_val};
                free(val.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_FROM_DECIMAL: {
                Value val = pop(vm);
                char* str = strdup(val.data.decimal_val);
                Value result = {.type = VAL_STRING, .data.string_val = str};
                free(val.data.decimal_val);
                push(vm, result);
                vm->ip++;
                break;
            }

            // MATH OPERATIONS

            case OP_MATH_SQRT_F64: {
                Value val = pop(vm);
                double result = sqrt(val.data.f64_val);
                Value res = {.type = VAL_F64, .data.f64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_POW_F64: {
                Value exp = pop(vm);
                Value base = pop(vm);
                double result = pow(base.data.f64_val, exp.data.f64_val);
                Value res = {.type = VAL_F64, .data.f64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_ABS_I64: {
                Value val = pop(vm);
                int64_t result = val.data.i64_val < 0 ? -val.data.i64_val : val.data.i64_val;
                Value res = {.type = VAL_I64, .data.i64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_ABS_F64: {
                Value val = pop(vm);
                double result = fabs(val.data.f64_val);
                Value res = {.type = VAL_F64, .data.f64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_MIN_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                int64_t result = a.data.i64_val < b.data.i64_val ? a.data.i64_val : b.data.i64_val;
                Value res = {.type = VAL_I64, .data.i64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_MIN_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                double result = a.data.f64_val < b.data.f64_val ? a.data.f64_val : b.data.f64_val;
                Value res = {.type = VAL_F64, .data.f64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_MAX_I64: {
                Value b = pop(vm);
                Value a = pop(vm);
                int64_t result = a.data.i64_val > b.data.i64_val ? a.data.i64_val : b.data.i64_val;
                Value res = {.type = VAL_I64, .data.i64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_MATH_MAX_F64: {
                Value b = pop(vm);
                Value a = pop(vm);
                double result = a.data.f64_val > b.data.f64_val ? a.data.f64_val : b.data.f64_val;
                Value res = {.type = VAL_F64, .data.f64_val = result};
                push(vm, res);
                vm->ip++;
                break;
            }

            case OP_HALT: {
                vm->running = false;
                break;
            }

            case OP_PRINT_DEBUG: {
                Value val = peek(vm, 0);
                printf("[DEBUG] ");
                switch (val.type) {
                    case VAL_INT:
                        printf("Int: %ld\n", val.data.int_val);
                        break;
                    case VAL_I8:
                        printf("I8: %d\n", val.data.i8_val);
                        break;
                    case VAL_I16:
                        printf("I16: %d\n", val.data.i16_val);
                        break;
                    case VAL_I32:
                        printf("I32: %d\n", val.data.i32_val);
                        break;
                    case VAL_I64:
                        printf("I64: %ld\n", val.data.i64_val);
                        break;
                    case VAL_U8:
                        printf("U8: %u\n", val.data.u8_val);
                        break;
                    case VAL_U16:
                        printf("U16: %u\n", val.data.u16_val);
                        break;
                    case VAL_U32:
                        printf("U32: %u\n", val.data.u32_val);
                        break;
                    case VAL_U64:
                        printf("U64: %lu\n", val.data.u64_val);
                        break;
                    case VAL_F32:
                        printf("F32: %.6f\n", val.data.f32_val);
                        break;
                    case VAL_F64:
                        printf("F64: %.15f\n", val.data.f64_val);
                        break;
                    case VAL_STRING:
                        printf("String: %s\n", val.data.string_val);
                        break;
                    case VAL_BOOL:
                        printf("Bool: %s\n", val.data.bool_val ? "true" : "false");
                        break;
                    case VAL_UNIT:
                        printf("Unit\n");
                        break;
                    default:
                        printf("Unknown type\n");
                }
                vm->ip++;
                break;
            }

            // SQLITE DATABASE OPERATIONS

            // PROCESS MANAGEMENT OPERATIONS

            case OP_PROCESS_SPAWN: {
                Value args_val = pop(vm);
                Value cmd_val = pop(vm);
                
                Array* args_arr = (Array*)args_val.data.ptr_val;
                const char** args = malloc(sizeof(char*) * (args_arr->count + 2));
                args[0] = cmd_val.data.string_val;
                for (uint32_t i = 0; i < args_arr->count; i++) {
                    args[i+1] = args_arr->items[i].data.string_val;
                }
                args[args_arr->count + 1] = NULL;
                
                Process* proc = process_spawn(cmd_val.data.string_val, args);
                
                free(args);
                free(cmd_val.data.string_val);
                
                Value result = {.type = VAL_PROCESS, .data.ptr_val = proc};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_PROCESS_EXEC: {
                Value args_val = pop(vm);
                Value cmd_val = pop(vm);
                
                Array* args_arr = (Array*)args_val.data.ptr_val;
                const char** args = malloc(sizeof(char*) * (args_arr->count + 2));
                args[0] = cmd_val.data.string_val;
                for (uint32_t i = 0; i < args_arr->count; i++) {
                    args[i+1] = args_arr->items[i].data.string_val;
                }
                args[args_arr->count + 1] = NULL;
                
                // Fork, exec, and wait for completion
                Process* proc = process_spawn(cmd_val.data.string_val, args);
                int exit_code = 0;
                if (proc) {
                    exit_code = process_wait(proc);
                } else {
                    exit_code = -1;
                }
                
                free(args);
                
                Value result = {.type = VAL_INT, .data.int_val = exit_code};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_PROCESS_WAIT: {
                Value proc_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a process
                if (proc_val.type != VAL_PROCESS) {
                    fprintf(stderr, "Runtime Error: process_wait expects a process handle, got type %d\n", proc_val.type);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Process* proc = (Process*)proc_val.data.ptr_val;
                
                // NULL CHECK: Ensure process pointer is valid
                if (!proc) {
                    fprintf(stderr, "Runtime Error: process_wait received NULL process pointer\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                int exit_code = process_wait(proc);
                Value result = {.type = VAL_INT, .data.i32_val = exit_code};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_PROCESS_KILL: {
                Value signal_val = pop(vm);
                Value proc_val = pop(vm);
                Process* proc = (Process*)proc_val.data.ptr_val;
                int signal = signal_val.data.i32_val;
                int result = process_kill(proc, signal);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_PROCESS_PIPE: {
                // Create pipe and return read/write fd pair
                int pipefd[2];
                if (pipe(pipefd) == -1) {
                    fprintf(stderr, "pipe failed: %s\n", strerror(errno));
                    Value unit = {.type = VAL_UNIT};
                    push(vm, unit);
                } else {
                    Array* arr = malloc(sizeof(Array));
                    arr->items = malloc(sizeof(Value) * 2);
                    arr->count = 2;
                    arr->capacity = 2;
                    arr->items[0].type = VAL_I32;
                    arr->items[0].data.i32_val = pipefd[0];
                    arr->items[1].type = VAL_I32;
                    arr->items[1].data.i32_val = pipefd[1];
                    Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                    push(vm, result);
                }
                vm->ip++;
                break;
            }

            case OP_PROCESS_READ: {
                Value proc_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a process
                if (proc_val.type != VAL_PROCESS) {
                    fprintf(stderr, "Runtime Error: process_read expects a process handle, got type %d\n", proc_val.type);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Process* proc = (Process*)proc_val.data.ptr_val;
                
                // NULL CHECK: Ensure process pointer is valid
                if (!proc) {
                    fprintf(stderr, "Runtime Error: process_read received NULL process pointer\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                char* output = process_read(proc);
                Value result = {.type = VAL_STRING, .data.string_val = output};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_PROCESS_WRITE: {
                Value data_val = pop(vm);
                Value proc_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a process
                if (proc_val.type != VAL_PROCESS) {
                    fprintf(stderr, "Runtime Error: process_write expects a process handle, got type %d\n", proc_val.type);
                    free(data_val.data.string_val);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Process* proc = (Process*)proc_val.data.ptr_val;
                
                // NULL CHECK: Ensure process pointer is valid
                if (!proc) {
                    fprintf(stderr, "Runtime Error: process_write received NULL process pointer\n");
                    free(data_val.data.string_val);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                int result = process_write(proc, data_val.data.string_val);
                free(data_val.data.string_val);
                Value result_val = {.type = VAL_BOOL, .data.bool_val = (result >= 0)};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            // NETWORK SOCKET OPERATIONS

            case OP_TCP_LISTEN: {
                Value port_val = pop(vm);
                int port = port_val.data.i32_val;
                Socket* sock = tcp_listen(port);
                
                // NULL CHECK: tcp_listen can return NULL on error
                if (!sock) {
                    fprintf(stderr, "Runtime Error: tcp_listen failed to create listening socket on port %d\n", port);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Value result = {.type = VAL_TCP_SOCKET, .data.ptr_val = sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_ACCEPT: {
                Value sock_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a TCP socket
                if (sock_val.type != VAL_TCP_SOCKET) {
                    fprintf(stderr, "Runtime Error: tcp_accept expects a TCP socket, got type %d\n", sock_val.type);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Socket* server_sock = (Socket*)sock_val.data.ptr_val;
                
                // NULL CHECK: Ensure socket pointer is valid
                if (!server_sock) {
                    fprintf(stderr, "Runtime Error: tcp_accept received NULL socket pointer\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Socket* client_sock = tcp_accept(server_sock);
                
                // NULL CHECK: tcp_accept can return NULL on error
                if (!client_sock) {
                    fprintf(stderr, "Runtime Error: tcp_accept failed to accept connection\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Value result = {.type = VAL_TCP_SOCKET, .data.ptr_val = client_sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_CONNECT: {
                Value port_val = pop(vm);
                Value host_val = pop(vm);
                int port = port_val.data.i32_val;
                
                Socket* sock = tcp_connect(host_val.data.string_val, port);
                free(host_val.data.string_val);
                
                // NULL CHECK: tcp_connect can return NULL on error
                if (!sock) {
                    fprintf(stderr, "Runtime Error: tcp_connect failed to connect to host:port\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Value result = {.type = VAL_TCP_SOCKET, .data.ptr_val = sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_TLS_CONNECT: {
                Value port_val = pop(vm);
                Value host_val = pop(vm);
                int port = port_val.data.i32_val;
                Socket* sock = tcp_tls_connect(host_val.data.string_val, port);
                free(host_val.data.string_val);
                Value result = {.type = VAL_TCP_SOCKET, .data.ptr_val = sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_SEND: {
                Value data_val = pop(vm);
                Value sock_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a TCP socket
                if (sock_val.type != VAL_TCP_SOCKET) {
                    fprintf(stderr, "Runtime Error: tcp_send expects a TCP socket, got type %d\n", sock_val.type);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                
                // NULL CHECK: Ensure socket pointer is valid
                if (!sock) {
                    fprintf(stderr, "Runtime Error: tcp_send received NULL socket pointer\n");
                    free(data_val.data.string_val);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                int result = tcp_send(sock, data_val.data.string_val);
                free(data_val.data.string_val);
                Value result_val = {.type = VAL_INT, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_TCP_RECEIVE: {
                Value max_bytes_val = pop(vm);
                Value sock_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a TCP socket, not a Process or other type
                if (sock_val.type != VAL_TCP_SOCKET) {
                    fprintf(stderr, "Runtime Error: tcp_receive expects a TCP socket, got type %d\n", sock_val.type);
                    fprintf(stderr, "This usually means you passed a process handle or other type to tcp_receive.\n");
                    fprintf(stderr, "Check that you're not mixing database handles with socket handles.\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                
                // NULL CHECK: Ensure socket pointer is valid
                if (!sock) {
                    fprintf(stderr, "Runtime Error: tcp_receive received NULL socket pointer\n");
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                int max_bytes = max_bytes_val.data.i32_val;
                char* data = tcp_receive(sock, max_bytes);
                Value result = {.type = VAL_STRING, .data.string_val = data};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_CLOSE: {
                Value sock_val = pop(vm);
                
                // TYPE SAFETY: Ensure we have a TCP socket
                if (sock_val.type != VAL_TCP_SOCKET) {
                    fprintf(stderr, "Runtime Error: tcp_close expects a TCP socket, got type %d\n", sock_val.type);
                    vm->running = false;
                    vm->exit_code = 1;
                    return 1;
                }
                
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                
                // NULL CHECK: tcp_close handles NULL gracefully, but we should still check
                if (!sock) {
                    fprintf(stderr, "Warning: tcp_close received NULL socket pointer\n");
                }
                
                tcp_close(sock);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_UDP_SOCKET: {
                Socket* sock = udp_socket();
                Value result = {.type = VAL_UDP_SOCKET, .data.ptr_val = sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_UDP_BIND: {
                Value port_val = pop(vm);
                Value sock_val = pop(vm);
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                int port = port_val.data.i32_val;
                int result = udp_bind(sock, port);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_UDP_SEND_TO: {
                Value port_val = pop(vm);
                Value host_val = pop(vm);
                Value data_val = pop(vm);
                Value sock_val = pop(vm);
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                
                struct sockaddr_in dest_addr;
                dest_addr.sin_family = AF_INET;
                dest_addr.sin_port = htons(port_val.data.i32_val);
                inet_pton(AF_INET, host_val.data.string_val, &dest_addr.sin_addr);
                
                int result = sendto(sock->sockfd, data_val.data.string_val, strlen(data_val.data.string_val), 0,
                                  (struct sockaddr*)&dest_addr, sizeof(dest_addr));
                
                free(host_val.data.string_val);
                free(data_val.data.string_val);
                
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_UDP_RECEIVE_FROM: {
                Value max_bytes_val = pop(vm);
                Value sock_val = pop(vm);
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                int max_bytes = max_bytes_val.data.i32_val;
                
                char* buffer = malloc(max_bytes + 1);
                struct sockaddr_in src_addr;
                socklen_t addr_len = sizeof(src_addr);
                
                int received = recvfrom(sock->sockfd, buffer, max_bytes, 0,
                                       (struct sockaddr*)&src_addr, &addr_len);
                
                if (received < 0) {
                    free(buffer);
                    Value unit = {.type = VAL_UNIT};
                    push(vm, unit);
                } else {
                    buffer[received] = '\0';
                    
                    // Return array: [data, host, port]
                    Array* arr = malloc(sizeof(Array));
                    arr->items = malloc(sizeof(Value) * 3);
                    arr->count = 3;
                    arr->capacity = 3;
                    
                    arr->items[0].type = VAL_STRING;
                    arr->items[0].data.string_val = buffer;
                    
                    arr->items[1].type = VAL_STRING;
                    char host[INET_ADDRSTRLEN];
                    inet_ntop(AF_INET, &src_addr.sin_addr, host, INET_ADDRSTRLEN);
                    arr->items[1].data.string_val = strdup(host);
                    
                    arr->items[2].type = VAL_I32;
                    arr->items[2].data.i32_val = ntohs(src_addr.sin_port);
                    
                    Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                    push(vm, result);
                }
                
                vm->ip++;
                break;
            }

            // CHANNEL OPERATIONS (Thread-Safe Queues)

            case OP_CHANNEL_NEW: {
                Value capacity_val = pop(vm);
                int capacity = capacity_val.data.int_val;
                Channel* ch = channel_new(capacity);
                Value result = {.type = VAL_CHANNEL, .data.ptr_val = ch};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_CHANNEL_SEND: {
                Value value_val = pop(vm);
                Value channel_val = pop(vm);
                Channel* ch = (Channel*)channel_val.data.ptr_val;
                channel_send(ch, value_val);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_CHANNEL_RECV: {
                Value channel_val = pop(vm);
                Channel* ch = (Channel*)channel_val.data.ptr_val;
                Value result = channel_recv(ch);
                push(vm, result);
                vm->ip++;
                break;
            }

            // GARBAGE COLLECTION OPERATIONS

            case OP_GC_COLLECT: {
                gc_collect(vm);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_GC_STATS: {
                // Return array: [bytes_allocated, next_gc]
                Array* arr = malloc(sizeof(Array));
                arr->items = malloc(sizeof(Value) * 2);
                arr->count = 2;
                arr->capacity = 2;
                
                arr->items[0].type = VAL_I64;
                arr->items[0].data.i64_val = vm->gc.bytes_allocated;
                
                arr->items[1].type = VAL_I64;
                arr->items[1].data.i64_val = vm->gc.next_gc;
                
                Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                push(vm, result);
                vm->ip++;
                break;
            }

            // FFI (FOREIGN FUNCTION INTERFACE) OPERATIONS
            
            case OP_FFI_LOAD: {
                // Load FFI library: library_name -> handle (0 on failure)
                Value lib_name_val = pop(vm);
                const char* lib_name = lib_name_val.data.string_val;
                
                void* handle = ffi_load_library(vm, lib_name);
                free(lib_name_val.data.string_val);
                
                Value result = {.type = VAL_FFI_HANDLE, .data.ptr_val = handle};
                push(vm, result);
                vm->ip++;
                break;
            }
            
            case OP_FFI_CALL: {
                // Call C function: arg_count handle func_name arg1 ... argN -> result
                // Stack layout: [arg_count] [handle] [func_name] [arg1] [arg2] ... [argN]
                Value arg_count_val = pop(vm);
                int arg_count = (int)arg_count_val.data.i64_val;
                
                // Pop arguments (in reverse order, so we need to collect them)
                Value* args = malloc(sizeof(Value) * arg_count);
                for (int i = arg_count - 1; i >= 0; i--) {
                    args[i] = pop(vm);
                }
                
                Value func_name_val = pop(vm);
                Value handle_val = pop(vm);
                
                void* handle = handle_val.data.ptr_val;
                const char* func_name = func_name_val.data.string_val;
                
                if (!handle) {
                    fprintf(stderr, "Error: Attempting to call FFI function '%s' with null handle\n", func_name);
                    free(args);
                    free(func_name_val.data.string_val);
                    return 1;
                }
                
                // Look up function (expect _aisl suffix)
                char full_func_name[256];
                if (strstr(func_name, "_aisl") == NULL) {
                    snprintf(full_func_name, sizeof(full_func_name), "%s_aisl", func_name);
                } else {
                    snprintf(full_func_name, sizeof(full_func_name), "%s", func_name);
                }
                
                void* func_ptr = dlsym(handle, full_func_name);
                if (!func_ptr) {
                    fprintf(stderr, "Error: FFI function '%s' not found in library: %s\n", 
                           full_func_name, dlerror());
                    free(args);
                    free(func_name_val.data.string_val);
                    return 1;
                }
                
                // Call function based on argument count
                // For now, support up to 3 arguments (can extend later)
                Value result;
                result.type = VAL_INT;  // Default return type
                
                if (arg_count == 0) {
                    int64_t (*f)() = (int64_t (*)())func_ptr;
                    result.data.i64_val = f();
                } else if (arg_count == 1) {
                    // Check argument type and call appropriately
                    if (args[0].type == VAL_STRING || args[0].type == VAL_I32 || 
                        args[0].type == VAL_I64 || args[0].type == VAL_INT) {
                        if (args[0].type == VAL_STRING) {
                            const char* (*f)(const char*) = (const char* (*)(const char*))func_ptr;
                            const char* ret = f(args[0].data.string_val);
                            if (ret) {
                                result.type = VAL_STRING;
                                result.data.string_val = strdup(ret);
                            } else {
                                result.type = VAL_INT;
                                result.data.i64_val = 0;
                            }
                        } else {
                            int64_t (*f)(int64_t) = (int64_t (*)(int64_t))func_ptr;
                            int64_t arg = (args[0].type == VAL_I32) ? args[0].data.i32_val : args[0].data.i64_val;
                            result.data.i64_val = f(arg);
                        }
                    }
                } else if (arg_count == 2) {
                    // Two string arguments -> string return (e.g., string_concat)
                    if (args[0].type == VAL_STRING && args[1].type == VAL_STRING) {
                        const char* (*f)(const char*, const char*) = 
                            (const char* (*)(const char*, const char*))func_ptr;
                        const char* ret = f(args[0].data.string_val, args[1].data.string_val);
                        if (ret) {
                            result.type = VAL_STRING;
                            result.data.string_val = strdup(ret);
                        } else {
                            result.type = VAL_INT;
                            result.data.i64_val = 0;
                        }
                    }
                    // Add more type combinations as needed
                } else if (arg_count == 3) {
                    // Three string arguments (e.g., string_replace)
                    if (args[0].type == VAL_STRING && args[1].type == VAL_STRING && args[2].type == VAL_STRING) {
                        const char* (*f)(const char*, const char*, const char*) = 
                            (const char* (*)(const char*, const char*, const char*))func_ptr;
                        const char* ret = f(args[0].data.string_val, args[1].data.string_val, args[2].data.string_val);
                        if (ret) {
                            result.type = VAL_STRING;
                            result.data.string_val = strdup(ret);
                        } else {
                            result.type = VAL_INT;
                            result.data.i64_val = 0;
                        }
                    }
                }
                
                // Free arguments
                for (int i = 0; i < arg_count; i++) {
                    if (args[i].type == VAL_STRING) {
                        free(args[i].data.string_val);
                    }
                }
                free(args);
                free(func_name_val.data.string_val);
                
                push(vm, result);
                vm->ip++;
                break;
            }
            
            case OP_FFI_AVAILABLE: {
                // Check if library is available: library_name -> bool
                Value lib_name_val = pop(vm);
                const char* lib_name = lib_name_val.data.string_val;
                
                bool available = ffi_is_available(lib_name);
                free(lib_name_val.data.string_val);
                
                Value result = {.type = VAL_BOOL, .data.bool_val = available};
                push(vm, result);
                vm->ip++;
                break;
            }
            
            case OP_FFI_CLOSE: {
                // Close library: handle -> unit
                Value handle_val = pop(vm);
                void* handle = handle_val.data.ptr_val;
                
                if (handle) {
                    ffi_close_library(vm, handle);
                }
                
                Value result = {.type = VAL_UNIT};
                push(vm, result);
                vm->ip++;
                break;
            }

            default:
                fprintf(stderr, "Unknown opcode: %d at ip=%d\n", inst.opcode, vm->ip);
                return 1;
        }
    }

    return vm->exit_code;
}

// DISASSEMBLER

void vm_disassemble(BytecodeProgram* program) {
    printf("=== AISL Bytecode Disassembly ===\n\n");

    printf("String Constants:\n");
    for (uint32_t i = 0; i < program->string_count; i++) {
        printf("  [%d] \"%s\"\n", i, program->string_constants[i]);
    }
    printf("\n");

    printf("Functions:\n");
    for (uint32_t i = 0; i < program->function_count; i++) {
        printf("  [%d] %s @ %d (locals: %d)\n",
               i,
               program->functions[i].name,
               program->functions[i].start_addr,
               program->functions[i].local_count);
    }
    printf("\n");

    printf("Instructions:\n");
    for (uint32_t i = 0; i < program->instruction_count; i++) {
        Instruction inst = program->instructions[i];
        printf("%04d: ", i);

        switch (inst.opcode) {
            case OP_PUSH_INT:
                printf("PUSH_INT %ld\n", inst.operand.int_val);
                break;
            case OP_PUSH_STRING:
                printf("PUSH_STRING [%d]\n", inst.operand.uint_val);
                break;
            case OP_PUSH_BOOL:
                printf("PUSH_BOOL %s\n", inst.operand.bool_val ? "true" : "false");
                break;
            case OP_PUSH_UNIT:
                printf("PUSH_UNIT\n");
                break;
            case OP_POP:
                printf("POP\n");
                break;
            case OP_DUP:
                printf("DUP\n");
                break;
            case OP_LOAD_LOCAL:
                printf("LOAD_LOCAL %d\n", inst.operand.uint_val);
                break;
            case OP_STORE_LOCAL:
                printf("STORE_LOCAL %d\n", inst.operand.uint_val);
                break;
                break;
                break;
                break;
                break;
                break;
            case OP_EQ_INT:
                printf("EQ_INT\n");
                break;
            case OP_NEQ_INT:
                printf("NEQ_INT\n");
                break;
            case OP_LT_INT:
                printf("LT_INT\n");
                break;
            case OP_GT_INT:
                printf("GT_INT\n");
                break;
            case OP_LTE_INT:
                printf("LTE_INT\n");
                break;
            case OP_GTE_INT:
                printf("GTE_INT\n");
                break;
            case OP_EQ_STR:
                printf("EQ_STR\n");
                break;
            case OP_NE_STR:
                printf("NE_STR\n");
                break;
            case OP_EQ_BOOL:
                printf("EQ_BOOL\n");
                break;
            case OP_NE_BOOL:
                printf("NE_BOOL\n");
                break;
            case OP_AND:
                printf("AND\n");
                break;
            case OP_OR:
                printf("OR\n");
                break;
            case OP_NOT:
                printf("NOT\n");
                break;
            case OP_JUMP:
                printf("JUMP -> %d\n", inst.operand.jump.target);
                break;
            case OP_JUMP_IF_FALSE:
                printf("JUMP_IF_FALSE -> %d\n", inst.operand.jump.target);
                break;
            case OP_CALL:
                printf("CALL fn=%d argc=%d\n", inst.operand.call.func_idx, inst.operand.call.arg_count);
                break;
            case OP_RETURN:
                printf("RETURN\n");
                break;
            case OP_IO_WRITE:
                printf("IO_WRITE\n");
                break;
            case OP_IO_READ:
                printf("IO_READ\n");
                break;
            case OP_IO_OPEN:
                printf("IO_OPEN\n");
                break;
            case OP_IO_CLOSE:
                printf("IO_CLOSE\n");
                break;
            case OP_STR_LEN:
                printf("STR_LEN\n");
                break;
            case OP_STR_CONCAT:
                printf("STR_CONCAT\n");
                break;
            case OP_STR_SLICE:
                printf("STR_SLICE\n");
                break;
            case OP_STR_GET:
                printf("STR_GET\n");
                break;
            case OP_STR_FROM_I64:
                printf("STR_FROM_I64\n");
                break;
            case OP_STR_FROM_F64:
                printf("STR_FROM_F64\n");
                break;
            // String operations removed (STR_SPLIT, STR_TRIM, STR_CONTAINS, STR_REPLACE, etc.)
            case OP_ARRAY_NEW:
                printf("ARRAY_NEW\n");
                break;
            case OP_ARRAY_PUSH:
                printf("ARRAY_PUSH\n");
                break;
            case OP_ARRAY_GET:
                printf("ARRAY_GET\n");
                break;
            case OP_ARRAY_SET:
                printf("ARRAY_SET\n");
                break;
            case OP_ARRAY_LEN:
                printf("ARRAY_LEN\n");
                break;
            case OP_HALT:
                printf("HALT\n");
                break;
            default:
                printf("UNKNOWN(%d)\n", inst.opcode);
        }
    }
}
