#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#define OPENSSL_API_COMPAT 0x10100000L
#include "vm.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <limits.h>
#include <sys/socket.h>
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

// SQLite support (optional)
#ifdef HAVE_SQLITE3
#include <sqlite3.h>
#else
// Stub types when SQLite is not available
typedef void sqlite3;
typedef void sqlite3_stmt;
#define SQLITE_OK 0
#define SQLITE_ROW 100
#define SQLITE_DONE 101
#define SQLITE_INTEGER 1
#define SQLITE_FLOAT 2
#define SQLITE_TEXT 3
#define SQLITE_NULL 5
#define SQLITE_TRANSIENT ((void(*)(void*))-1)
#endif

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
    int status_code;
    char* body;
    size_t body_length;
    Map* headers;
} HttpResponse;

typedef struct {
    int sockfd;
    SSL* ssl;
    SSL_CTX* ssl_ctx;
    int connected;
} WebSocket;

typedef struct {
    regex_t compiled;
    char* pattern;
} RegexValue;

typedef struct {
    sqlite3* db;
} SqliteDB;

typedef struct {
    sqlite3_stmt* stmt;
} SqliteStmt;

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
} Socket;

typedef struct {
    bool completed;
    Value result;
    pthread_t thread;
} Future;

// ============================================
// GARBAGE COLLECTOR IMPLEMENTATION
// ============================================

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
        val.type == VAL_HTTP_RESPONSE || val.type == VAL_WEBSOCKET ||
        val.type == VAL_REGEX || val.type == VAL_SQLITE_DB || 
        val.type == VAL_SQLITE_STMT || val.type == VAL_PROCESS ||
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
    return val;
}

// ============================================
// JSON HELPER FUNCTIONS
// ============================================

static JsonValue* json_new(JsonType type) {
    JsonValue* json = malloc(sizeof(JsonValue));
    json->type = type;
    json->length = 0;
    if (type == JSON_ARRAY) {
        json->data.array_items = NULL;
    } else if (type == JSON_OBJECT) {
        json->data.object_entries = NULL;
    }
    return json;
}

static void json_free(JsonValue* json) {
    if (!json) return;
    
    switch (json->type) {
        case JSON_STRING:
            free(json->data.string_val);
            break;
        case JSON_ARRAY: {
            JsonArrayItem* item = json->data.array_items;
            while (item) {
                JsonArrayItem* next = item->next;
                json_free(item->value);
                free(item);
                item = next;
            }
            break;
        }
        case JSON_OBJECT: {
            JsonObjectEntry* entry = json->data.object_entries;
            while (entry) {
                JsonObjectEntry* next = entry->next;
                free(entry->key);
                json_free(entry->value);
                free(entry);
                entry = next;
            }
            break;
        }
        default:
            break;
    }
    free(json);
}

static void json_object_set(JsonValue* obj, const char* key, JsonValue* value) {
    if (obj->type != JSON_OBJECT) return;
    
    JsonObjectEntry* entry = obj->data.object_entries;
    while (entry) {
        if (strcmp(entry->key, key) == 0) {
            json_free(entry->value);
            entry->value = value;
            return;
        }
        entry = entry->next;
    }
    
    JsonObjectEntry* new_entry = malloc(sizeof(JsonObjectEntry));
    new_entry->key = strdup(key);
    new_entry->value = value;
    new_entry->next = obj->data.object_entries;
    obj->data.object_entries = new_entry;
    obj->length++;
}

static JsonValue* json_object_get(JsonValue* obj, const char* key) {
    if (obj->type != JSON_OBJECT) return NULL;
    
    JsonObjectEntry* entry = obj->data.object_entries;
    while (entry) {
        if (strcmp(entry->key, key) == 0) {
            return entry->value;
        }
        entry = entry->next;
    }
    return NULL;
}

static void json_array_push(JsonValue* arr, JsonValue* value) {
    if (arr->type != JSON_ARRAY) return;
    
    JsonArrayItem* new_item = malloc(sizeof(JsonArrayItem));
    new_item->value = value;
    new_item->next = NULL;
    
    if (arr->data.array_items == NULL) {
        arr->data.array_items = new_item;
    } else {
        // Add at end
        JsonArrayItem* item = arr->data.array_items;
        while (item->next) item = item->next;
        item->next = new_item;
    }
    arr->length++;
}

static JsonValue* json_array_get(JsonValue* arr, uint32_t index) {
    if (arr->type != JSON_ARRAY) return NULL;
    
    JsonArrayItem* item = arr->data.array_items;
    for (uint32_t i = 0; i < index && item; i++) {
        item = item->next;
    }
    return item ? item->value : NULL;
}

// Simple JSON parser (very basic, handles common cases)
static const char* json_skip_whitespace(const char* str) {
    while (*str && isspace(*str)) str++;
    return str;
}

static JsonValue* json_parse_value(const char** str);

static JsonValue* json_parse_string(const char** str) {
    (*str)++;  // Skip opening quote
    const char* start = *str;
    while (**str && **str != '"') {
        if (**str == '\\') (*str)++;  // Skip escaped char
        (*str)++;
    }
    if (**str != '"') return NULL;  // Error
    
    size_t len = *str - start;
    char* string_val = malloc(len + 1);
    memcpy(string_val, start, len);
    string_val[len] = '\0';
    (*str)++;  // Skip closing quote
    
    JsonValue* json = json_new(JSON_STRING);
    json->data.string_val = string_val;
    return json;
}

static JsonValue* json_parse_number(const char** str) {
    char* end;
    double num = strtod(*str, &end);
    if (end == *str) return NULL;  // Error
    *str = end;
    
    JsonValue* json = json_new(JSON_NUMBER);
    json->data.number_val = num;
    return json;
}

static JsonValue* json_parse_array(const char** str) {
    (*str)++;  // Skip '['
    *str = json_skip_whitespace(*str);
    
    JsonValue* arr = json_new(JSON_ARRAY);
    
    if (**str == ']') {
        (*str)++;
        return arr;
    }
    
    while (true) {
        JsonValue* value = json_parse_value(str);
        if (!value) {
            json_free(arr);
            return NULL;
        }
        json_array_push(arr, value);
        
        *str = json_skip_whitespace(*str);
        if (**str == ',') {
            (*str)++;
            *str = json_skip_whitespace(*str);
        } else if (**str == ']') {
            (*str)++;
            break;
        } else {
            json_free(arr);
            return NULL;
        }
    }
    
    return arr;
}

static JsonValue* json_parse_object(const char** str) {
    (*str)++;  // Skip '{'
    *str = json_skip_whitespace(*str);
    
    JsonValue* obj = json_new(JSON_OBJECT);
    
    if (**str == '}') {
        (*str)++;
        return obj;
    }
    
    while (true) {
        *str = json_skip_whitespace(*str);
        if (**str != '"') {
            json_free(obj);
            return NULL;
        }
        
        JsonValue* key_json = json_parse_string(str);
        if (!key_json) {
            json_free(obj);
            return NULL;
        }
        char* key = key_json->data.string_val;
        key_json->data.string_val = NULL;
        json_free(key_json);
        
        *str = json_skip_whitespace(*str);
        if (**str != ':') {
            free(key);
            json_free(obj);
            return NULL;
        }
        (*str)++;
        
        JsonValue* value = json_parse_value(str);
        if (!value) {
            free(key);
            json_free(obj);
            return NULL;
        }
        
        json_object_set(obj, key, value);
        free(key);
        
        *str = json_skip_whitespace(*str);
        if (**str == ',') {
            (*str)++;
        } else if (**str == '}') {
            (*str)++;
            break;
        } else {
            json_free(obj);
            return NULL;
        }
    }
    
    return obj;
}

static JsonValue* json_parse_value(const char** str) {
    *str = json_skip_whitespace(*str);
    
    if (**str == '"') {
        return json_parse_string(str);
    } else if (**str == '{') {
        return json_parse_object(str);
    } else if (**str == '[') {
        return json_parse_array(str);
    } else if (strncmp(*str, "true", 4) == 0) {
        *str += 4;
        JsonValue* json = json_new(JSON_BOOL);
        json->data.bool_val = true;
        return json;
    } else if (strncmp(*str, "false", 5) == 0) {
        *str += 5;
        JsonValue* json = json_new(JSON_BOOL);
        json->data.bool_val = false;
        return json;
    } else if (strncmp(*str, "null", 4) == 0) {
        *str += 4;
        return json_new(JSON_NULL);
    } else if (**str == '-' || isdigit(**str)) {
        return json_parse_number(str);
    }
    
    return NULL;
}

static JsonValue* json_parse(const char* str) {
    return json_parse_value(&str);
}

// JSON stringify (convert to string)
static void json_stringify_impl(JsonValue* json, char** buf, size_t* pos, size_t* cap) {
    #define ENSURE_CAP(n) \
        while (*pos + (n) >= *cap) { \
            *cap *= 2; \
            *buf = realloc(*buf, *cap); \
        }
    
    #define APPEND(s, len) \
        ENSURE_CAP(len); \
        memcpy(*buf + *pos, s, len); \
        *pos += len;
    
    switch (json->type) {
        case JSON_NULL:
            APPEND("null", 4);
            break;
        case JSON_BOOL:
            if (json->data.bool_val) {
                APPEND("true", 4);
            } else {
                APPEND("false", 5);
            }
            break;
        case JSON_NUMBER: {
            char num_buf[64];
            int len = snprintf(num_buf, sizeof(num_buf), "%.15g", json->data.number_val);
            APPEND(num_buf, len);
            break;
        }
        case JSON_STRING: {
            APPEND("\"", 1);
            const char* s = json->data.string_val;
            while (*s) {
                if (*s == '"' || *s == '\\') {
                    ENSURE_CAP(2);
                    (*buf)[(*pos)++] = '\\';
                    (*buf)[(*pos)++] = *s;
                } else {
                    ENSURE_CAP(1);
                    (*buf)[(*pos)++] = *s;
                }
                s++;
            }
            APPEND("\"", 1);
            break;
        }
        case JSON_ARRAY: {
            APPEND("[", 1);
            JsonArrayItem* item = json->data.array_items;
            int is_first = 1;
            while (item) {
                if (!is_first) {
                    APPEND(",", 1);
                }
                is_first = 0;
                json_stringify_impl(item->value, buf, pos, cap);
                item = item->next;
            }
            APPEND("]", 1);
            break;
        }
        case JSON_OBJECT: {
            APPEND("{", 1);
            JsonObjectEntry* entry = json->data.object_entries;
            int is_first = 1;
            while (entry) {
                if (!is_first) {
                    APPEND(",", 1);
                }
                is_first = 0;
                
                APPEND("\"", 1);
                APPEND(entry->key, strlen(entry->key));
                APPEND("\":", 2);
                json_stringify_impl(entry->value, buf, pos, cap);
                entry = entry->next;
            }
            APPEND("}", 1);
            break;
        }
    }
    
    #undef ENSURE_CAP
    #undef APPEND
}

static char* json_stringify(JsonValue* json) {
    size_t cap = 256;
    size_t pos = 0;
    char* buf = malloc(cap);
    json_stringify_impl(json, &buf, &pos, &cap);
    buf[pos] = '\0';
    return buf;
}

static HttpResponse* http_response_new() {
    HttpResponse* resp = malloc(sizeof(HttpResponse));
    resp->status_code = 0;
    resp->body = NULL;
    resp->body_length = 0;
    resp->headers = NULL;
    return resp;
}

static void http_response_free(HttpResponse* resp) __attribute__((unused));
static void http_response_free(HttpResponse* resp) {
    if (!resp) return;
    free(resp->body);
    free(resp);
}

static int ssl_initialized = 0;

static void init_openssl() {
    if (!ssl_initialized) {
        SSL_load_error_strings();
        SSL_library_init();
        OpenSSL_add_all_algorithms();
        ssl_initialized = 1;
    }
}

static HttpResponse* http_request(const char* method, const char* url, const char* body) {
    init_openssl();
    HttpResponse* resp = http_response_new();
    
    char host[256] = {0};
    char path[1024] = "/";
    int port = 80;
    int use_https = 0;
    
    if (strncmp(url, "https://", 8) == 0) {
        use_https = 1;
        port = 443;
        sscanf(url + 8, "%255[^/]%1023s", host, path);
    } else if (strncmp(url, "http://", 7) == 0) {
        sscanf(url + 7, "%255[^/]%1023s", host, path);
    } else {
        resp->status_code = -1;
        return resp;
    }
    
    struct hostent* server = gethostbyname(host);
    if (server == NULL) {
        resp->status_code = -3;
        return resp;
    }
    
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {
        resp->status_code = -4;
        return resp;
    }
    
    struct sockaddr_in serv_addr;
    memset(&serv_addr, 0, sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    memcpy(&serv_addr.sin_addr.s_addr, server->h_addr_list[0], server->h_length);
    serv_addr.sin_port = htons(port);
    
    if (connect(sockfd, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) < 0) {
        close(sockfd);
        resp->status_code = -5;
        return resp;
    }
    
    SSL* ssl = NULL;
    SSL_CTX* ssl_ctx = NULL;
    
    if (use_https) {
        ssl_ctx = SSL_CTX_new(TLS_client_method());
        if (!ssl_ctx) {
            close(sockfd);
            resp->status_code = -8;
            return resp;
        }
        
        ssl = SSL_new(ssl_ctx);
        SSL_set_fd(ssl, sockfd);
        
        if (SSL_connect(ssl) != 1) {
            SSL_free(ssl);
            SSL_CTX_free(ssl_ctx);
            close(sockfd);
            resp->status_code = -9;
            return resp;
        }
    }
    
    char request[4096];
    int body_len = body ? strlen(body) : 0;
    snprintf(request, sizeof(request),
        "%s %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n%s%s\r\n%s",
        method, path, host,
        body_len > 0 ? "Content-Length: " : "",
        body_len > 0 ? (char[]){body_len / 100 + '0', (body_len / 10) % 10 + '0', body_len % 10 + '0', '\0'} : "",
        body ? body : "");
    
    ssize_t sent;
    if (use_https) {
        sent = SSL_write(ssl, request, strlen(request));
    } else {
        sent = write(sockfd, request, strlen(request));
    }
    
    if (sent < 0) {
        if (use_https) {
            SSL_free(ssl);
            SSL_CTX_free(ssl_ctx);
        }
        close(sockfd);
        resp->status_code = -6;
        return resp;
    }
    
    size_t response_cap = 4096;
    size_t response_len = 0;
    char* response_buf = malloc(response_cap);
    
    ssize_t n;
    while (1) {
        if (use_https) {
            n = SSL_read(ssl, response_buf + response_len, response_cap - response_len - 1);
        } else {
            n = read(sockfd, response_buf + response_len, response_cap - response_len - 1);
        }
        
        if (n <= 0) break;
        
        response_len += n;
        if (response_len + 1024 > response_cap) {
            response_cap *= 2;
            response_buf = realloc(response_buf, response_cap);
        }
    }
    
    if (use_https) {
        SSL_free(ssl);
        SSL_CTX_free(ssl_ctx);
    }
    close(sockfd);
    response_buf[response_len] = '\0';
    
    char* body_start = strstr(response_buf, "\r\n\r\n");
    if (body_start) {
        body_start += 4;
        resp->body = strdup(body_start);
        resp->body_length = strlen(resp->body);
        *body_start = '\0';
    }
    
    if (sscanf(response_buf, "HTTP/1.%*d %d", &resp->status_code) != 1) {
        resp->status_code = -7;
    }
    
    free(response_buf);
    return resp;
}

static HttpResponse* http_get(const char* url) {
    return http_request("GET", url, NULL);
}

static HttpResponse* http_post(const char* url, const char* body) {
    return http_request("POST", url, body);
}

static HttpResponse* http_put(const char* url, const char* body) {
    return http_request("PUT", url, body);
}

static HttpResponse* http_delete(const char* url) {
    return http_request("DELETE", url, NULL);
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

static const char base64_chars[] = 
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static char* base64_encode(const char* input) {
    size_t len = strlen(input);
    size_t output_len = 4 * ((len + 2) / 3);
    char* output = malloc(output_len + 1);
    
    size_t i, j;
    for (i = 0, j = 0; i < len;) {
        uint32_t octet_a = i < len ? (unsigned char)input[i++] : 0;
        uint32_t octet_b = i < len ? (unsigned char)input[i++] : 0;
        uint32_t octet_c = i < len ? (unsigned char)input[i++] : 0;
        
        uint32_t triple = (octet_a << 16) + (octet_b << 8) + octet_c;
        
        output[j++] = base64_chars[(triple >> 18) & 0x3F];
        output[j++] = base64_chars[(triple >> 12) & 0x3F];
        output[j++] = base64_chars[(triple >> 6) & 0x3F];
        output[j++] = base64_chars[triple & 0x3F];
    }
    
    for (i = 0; i < (3 - len % 3) % 3; i++) {
        output[output_len - 1 - i] = '=';
    }
    
    output[output_len] = '\0';
    return output;
}

static char* base64_decode(const char* input) {
    size_t len = strlen(input);
    size_t output_len = len / 4 * 3;
    if (input[len - 1] == '=') output_len--;
    if (input[len - 2] == '=') output_len--;
    
    char* output = malloc(output_len + 1);
    
    unsigned char decode_table[256] = {0};
    for (int i = 0; i < 64; i++) {
        decode_table[(unsigned char)base64_chars[i]] = i;
    }
    
    size_t i, j;
    for (i = 0, j = 0; i < len;) {
        uint32_t sextet_a = input[i] == '=' ? 0 : decode_table[(unsigned char)input[i]]; i++;
        uint32_t sextet_b = input[i] == '=' ? 0 : decode_table[(unsigned char)input[i]]; i++;
        uint32_t sextet_c = input[i] == '=' ? 0 : decode_table[(unsigned char)input[i]]; i++;
        uint32_t sextet_d = input[i] == '=' ? 0 : decode_table[(unsigned char)input[i]]; i++;
        
        uint32_t triple = (sextet_a << 18) + (sextet_b << 12) + (sextet_c << 6) + sextet_d;
        
        if (j < output_len) output[j++] = (triple >> 16) & 0xFF;
        if (j < output_len) output[j++] = (triple >> 8) & 0xFF;
        if (j < output_len) output[j++] = triple & 0xFF;
    }
    
    output[output_len] = '\0';
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

// ============================================
// WEBSOCKET IMPLEMENTATION
// ============================================

static WebSocket* ws_connect(const char* url) {
    init_openssl();
    
    WebSocket* ws = malloc(sizeof(WebSocket));
    ws->ssl = NULL;
    ws->ssl_ctx = NULL;
    ws->connected = 0;
    
    char host[256] = {0};
    char path[1024] = "/";
    int port = 80;
    int use_wss = 0;
    
    if (strncmp(url, "wss://", 6) == 0) {
        use_wss = 1;
        port = 443;
        sscanf(url + 6, "%255[^/]%1023s", host, path);
    } else if (strncmp(url, "ws://", 5) == 0) {
        sscanf(url + 5, "%255[^/]%1023s", host, path);
    } else {
        return ws;
    }
    
    struct hostent* server = gethostbyname(host);
    if (!server) return ws;
    
    ws->sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (ws->sockfd < 0) return ws;
    
    struct sockaddr_in serv_addr;
    memset(&serv_addr, 0, sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    memcpy(&serv_addr.sin_addr.s_addr, server->h_addr_list[0], server->h_length);
    serv_addr.sin_port = htons(port);
    
    if (connect(ws->sockfd, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) < 0) {
        close(ws->sockfd);
        return ws;
    }
    
    if (use_wss) {
        ws->ssl_ctx = SSL_CTX_new(TLS_client_method());
        if (!ws->ssl_ctx) {
            close(ws->sockfd);
            return ws;
        }
        ws->ssl = SSL_new(ws->ssl_ctx);
        SSL_set_fd(ws->ssl, ws->sockfd);
        if (SSL_connect(ws->ssl) != 1) {
            SSL_free(ws->ssl);
            SSL_CTX_free(ws->ssl_ctx);
            close(ws->sockfd);
            return ws;
        }
    }
    
    char handshake[1024];
    snprintf(handshake, sizeof(handshake),
        "GET %s HTTP/1.1\r\n"
        "Host: %s\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n",
        path, host);
    
    if (use_wss) {
        SSL_write(ws->ssl, handshake, strlen(handshake));
    } else {
        write(ws->sockfd, handshake, strlen(handshake));
    }
    
    char response[2048];
    int n;
    if (use_wss) {
        n = SSL_read(ws->ssl, response, sizeof(response) - 1);
    } else {
        n = read(ws->sockfd, response, sizeof(response) - 1);
    }
    
    if (n > 0) {
        response[n] = '\0';
        if (strstr(response, "101 Switching Protocols")) {
            ws->connected = 1;
        }
    }
    
    return ws;
}

static int ws_send(WebSocket* ws, const char* message) {
    if (!ws || !ws->connected) return 0;
    
    size_t len = strlen(message);
    unsigned char frame[10];
    int frame_size = 0;
    
    frame[0] = 0x81;
    if (len < 126) {
        frame[1] = 0x80 | len;
        frame_size = 2;
    } else if (len < 65536) {
        frame[1] = 0x80 | 126;
        frame[2] = (len >> 8) & 0xFF;
        frame[3] = len & 0xFF;
        frame_size = 4;
    } else {
        frame[1] = 0x80 | 127;
        for (int i = 0; i < 8; i++) {
            frame[2 + i] = (len >> (56 - i * 8)) & 0xFF;
        }
        frame_size = 10;
    }
    
    unsigned char mask[4] = {0x12, 0x34, 0x56, 0x78};
    memcpy(frame + frame_size, mask, 4);
    frame_size += 4;
    
    unsigned char* masked = malloc(len);
    for (size_t i = 0; i < len; i++) {
        masked[i] = message[i] ^ mask[i % 4];
    }
    
    int sent = 0;
    if (ws->ssl) {
        sent = SSL_write(ws->ssl, frame, frame_size);
        sent += SSL_write(ws->ssl, masked, len);
    } else {
        sent = write(ws->sockfd, frame, frame_size);
        sent += write(ws->sockfd, masked, len);
    }
    
    free(masked);
    return sent > 0;
}

static char* ws_receive(WebSocket* ws) {
    if (!ws || !ws->connected) return strdup("");
    
    unsigned char header[2];
    int n;
    
    if (ws->ssl) {
        n = SSL_read(ws->ssl, header, 2);
    } else {
        n = read(ws->sockfd, header, 2);
    }
    
    if (n < 2) return strdup("");
    
    uint64_t payload_len = header[1] & 0x7F;
    if (payload_len == 126) {
        unsigned char len_bytes[2];
        if (ws->ssl) {
            SSL_read(ws->ssl, len_bytes, 2);
        } else {
            read(ws->sockfd, len_bytes, 2);
        }
        payload_len = (len_bytes[0] << 8) | len_bytes[1];
    } else if (payload_len == 127) {
        unsigned char len_bytes[8];
        if (ws->ssl) {
            SSL_read(ws->ssl, len_bytes, 8);
        } else {
            read(ws->sockfd, len_bytes, 8);
        }
        payload_len = 0;
        for (int i = 0; i < 8; i++) {
            payload_len = (payload_len << 8) | len_bytes[i];
        }
    }
    
    char* payload = malloc(payload_len + 1);
    if (ws->ssl) {
        SSL_read(ws->ssl, payload, payload_len);
    } else {
        read(ws->sockfd, payload, payload_len);
    }
    payload[payload_len] = '\0';
    
    return payload;
}

static void ws_close(WebSocket* ws) {
    if (!ws) return;
    
    if (ws->ssl) {
        SSL_free(ws->ssl);
        SSL_CTX_free(ws->ssl_ctx);
    }
    close(ws->sockfd);
    free(ws);
}

// ============================================
// SQLITE IMPLEMENTATION
// ============================================

// ============================================
// SQLITE IMPLEMENTATION
// ============================================

#ifdef HAVE_SQLITE3

static SqliteDB* sqlite_open(const char* path) {
    SqliteDB* db = malloc(sizeof(SqliteDB));
    int rc = sqlite3_open(path, &db->db);
    if (rc != SQLITE_OK) {
        sqlite3_close(db->db);
        free(db);
        return NULL;
    }
    return db;
}

static void sqlite_close(SqliteDB* db) {
    if (!db) return;
    sqlite3_close(db->db);
    free(db);
}

static int sqlite_exec(SqliteDB* db, const char* sql) {
    if (!db) return 0;
    char* err_msg = NULL;
    int rc = sqlite3_exec(db->db, sql, NULL, NULL, &err_msg);
    if (err_msg) sqlite3_free(err_msg);
    return rc == SQLITE_OK;
}

static Array* sqlite_query(SqliteDB* db, const char* sql) {
    if (!db) return NULL;
    
    Array* results = malloc(sizeof(Array));
    results->capacity = 16;
    results->count = 0;
    results->items = malloc(sizeof(Value) * results->capacity);
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db->db, sql, -1, &stmt, NULL);
    if (rc != SQLITE_OK) {
        free(results->items);
        free(results);
        return NULL;
    }
    
    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        int col_count = sqlite3_column_count(stmt);
        Array* row = malloc(sizeof(Array));
        row->capacity = col_count;
        row->count = col_count;
        row->items = malloc(sizeof(Value) * col_count);
        
        for (int i = 0; i < col_count; i++) {
            int type = sqlite3_column_type(stmt, i);
            if (type == SQLITE_INTEGER) {
                row->items[i].type = VAL_I64;
                row->items[i].data.i64_val = sqlite3_column_int64(stmt, i);
            } else if (type == SQLITE_FLOAT) {
                row->items[i].type = VAL_F64;
                row->items[i].data.f64_val = sqlite3_column_double(stmt, i);
            } else if (type == SQLITE_TEXT) {
                row->items[i].type = VAL_STRING;
                const char* text = (const char*)sqlite3_column_text(stmt, i);
                row->items[i].data.string_val = strdup(text ? text : "");
            } else {
                row->items[i].type = VAL_UNIT;
            }
        }
        
        if (results->count >= results->capacity) {
            results->capacity *= 2;
            results->items = realloc(results->items, sizeof(Value) * results->capacity);
        }
        
        Value row_val = {.type = VAL_ARRAY, .data.ptr_val = row};
        results->items[results->count++] = row_val;
    }
    
    sqlite3_finalize(stmt);
    return results;
}

static SqliteStmt* sqlite_prepare(SqliteDB* db, const char* sql) {
    if (!db) return NULL;
    
    SqliteStmt* stmt_wrapper = malloc(sizeof(SqliteStmt));
    int rc = sqlite3_prepare_v2(db->db, sql, -1, &stmt_wrapper->stmt, NULL);
    if (rc != SQLITE_OK) {
        free(stmt_wrapper);
        return NULL;
    }
    return stmt_wrapper;
}

#else

// Stub implementations when SQLite is not available
static SqliteDB* sqlite_open(const char* path) {
    (void)path;
    fprintf(stderr, "SQLite support not compiled in\n");
    return NULL;
}

static void sqlite_close(SqliteDB* db) {
    (void)db;
}

static int sqlite_exec(SqliteDB* db, const char* sql) {
    (void)db; (void)sql;
    fprintf(stderr, "SQLite support not compiled in\n");
    return 0;
}

static Array* sqlite_query(SqliteDB* db, const char* sql) {
    (void)db; (void)sql;
    fprintf(stderr, "SQLite support not compiled in\n");
    return NULL;
}

static SqliteStmt* sqlite_prepare(SqliteDB* db, const char* sql) {
    (void)db; (void)sql;
    fprintf(stderr, "SQLite support not compiled in\n");
    return NULL;
}

#endif

// ============================================
// PROCESS IMPLEMENTATION
// ============================================

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
    
    char buffer[4096];
    ssize_t n = read(proc->stdout_fd, buffer, sizeof(buffer) - 1);
    if (n < 0) return strdup("");
    
    buffer[n] = '\0';
    return strdup(buffer);
}

static int process_write(Process* proc, const char* data) {
    if (!proc) return 0;
    
    ssize_t n = write(proc->stdin_fd, data, strlen(data));
    return n > 0;
}

// ============================================
// NETWORK SOCKET IMPLEMENTATION
// ============================================

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

static int tcp_send(Socket* sock, const char* data) {
    if (!sock) return -1;
    return send(sock->sockfd, data, strlen(data), 0);
}

static char* tcp_receive(Socket* sock, int max_bytes) {
    if (!sock) return strdup("");
    
    char* buffer = malloc(max_bytes + 1);
    ssize_t n = recv(sock->sockfd, buffer, max_bytes, 0);
    
    if (n < 0) {
        free(buffer);
        return strdup("");
    }
    
    buffer[n] = '\0';
    return buffer;
}

static void tcp_close(Socket* sock) {
    if (!sock) return;
    close(sock->sockfd);
    free(sock);
}

static Socket* udp_socket() {
    Socket* sock = malloc(sizeof(Socket));
    sock->is_udp = true;
    
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

VM* vm_new(BytecodeProgram* program) {
    VM* vm = malloc(sizeof(VM));
    vm->program = program;
    vm->ip = 0;
    vm->sp = 0;
    vm->call_sp = 0;
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
    
    free(vm->globals);
    free(vm);
}

// ============================================
// FFI (FOREIGN FUNCTION INTERFACE) OPERATIONS
// ============================================

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

// ============================================
// STACK OPERATIONS
// ============================================

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

// ============================================
// VM EXECUTION
// ============================================

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


            case OP_PUSH_F64:
            case OP_PUSH_FLOAT: {
                Value val = {.type = VAL_F64, .data.f64_val = inst.operand.float_val};
                push(vm, val);
                vm->ip++;
                break;
            }

            case OP_POP: {
                Value val = pop(vm);
                if (val.type == VAL_STRING) {
                    free(val.data.string_val);
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
                push(vm, value_clone(val));
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
                vm->stack[fp + idx] = val;
                vm->ip++;
                break;
            }

            // ============================================
            // ============================================
            // INT (I64) ARITHMETIC (v6.0 - removed i32)
            // ============================================

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

            // ============================================
            // TYPED F32 ARITHMETIC
            // ============================================

            // ============================================
            // FLOAT (F64) ARITHMETIC - AISL 'float' type
            // ============================================

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

            // ============================================
            // INT (I64) COMPARISONS (v6.0 - removed i32)
            // ============================================

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

            // ============================================
            // FLOAT (F64) COMPARISONS - AISL 'float' type
            // ============================================

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

                if (vm->call_sp >= CALL_STACK_SIZE) {
                    fprintf(stderr, "Call stack overflow\n");
                    return 1;
                }
                if (vm->sp < arg_count) {
                    fprintf(stderr, "Stack underflow on call\n");
                    return 1;
                }

                uint32_t fp = vm->sp - arg_count;
                CallFrame frame = {
                    .return_addr = vm->ip + 1,
                    .frame_pointer = fp,
                    .local_count = vm->program->functions[func_idx].local_count
                };
                vm->call_stack[vm->call_sp++] = frame;

                while (vm->sp < fp + frame.local_count) {
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

            case OP_STR_SPLIT: {
                Value delim = pop(vm);
                Value str = pop(vm);
                const char* s = str.data.string_val;
                const char* d = delim.data.string_val;
                size_t delim_len = strlen(d);
                
                // Create array to hold split results
                Array* arr = malloc(sizeof(Array));
                arr->count = 0;
                arr->capacity = 8;
                arr->items = malloc(sizeof(Value) * arr->capacity);
                
                if (delim_len == 0) {
                    // Empty delimiter: return array with original string
                    Value elem = {.type = VAL_STRING, .data.string_val = strdup(s)};
                    arr->items[arr->count++] = elem;
                } else {
                    const char* start = s;
                    const char* found;
                    while ((found = strstr(start, d)) != NULL) {
                        // Found delimiter
                        size_t len = found - start;
                        char* part = malloc(len + 1);
                        memcpy(part, start, len);
                        part[len] = '\0';
                        
                        if (arr->count >= arr->capacity) {
                            arr->capacity *= 2;
                            arr->items = realloc(arr->items, sizeof(Value) * arr->capacity);
                        }
                        Value elem = {.type = VAL_STRING, .data.string_val = part};
                        arr->items[arr->count++] = elem;
                        start = found + delim_len;
                    }
                    // Add remaining part
                    char* part = strdup(start);
                    if (arr->count >= arr->capacity) {
                        arr->capacity *= 2;
                        arr->items = realloc(arr->items, sizeof(Value) * arr->capacity);
                    }
                    Value elem = {.type = VAL_STRING, .data.string_val = part};
                    arr->items[arr->count++] = elem;
                }
                
                free(str.data.string_val);
                free(delim.data.string_val);
                Value result = {.type = VAL_ARRAY, .data.ptr_val = arr};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_TRIM: {
                Value str = pop(vm);
                const char* s = str.data.string_val;
                size_t len = strlen(s);
                
                // Find start (skip leading whitespace)
                size_t start = 0;
                while (start < len && isspace((unsigned char)s[start])) {
                    start++;
                }
                
                // Find end (skip trailing whitespace)
                size_t end = len;
                while (end > start && isspace((unsigned char)s[end - 1])) {
                    end--;
                }
                
                // Create trimmed string
                size_t trimmed_len = end - start;
                char* trimmed = malloc(trimmed_len + 1);
                memcpy(trimmed, s + start, trimmed_len);
                trimmed[trimmed_len] = '\0';
                
                free(str.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = trimmed};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_CONTAINS: {
                Value needle = pop(vm);
                Value haystack = pop(vm);
                const char* h = haystack.data.string_val;
                const char* n = needle.data.string_val;
                
                bool found = (strstr(h, n) != NULL);
                
                free(haystack.data.string_val);
                free(needle.data.string_val);
                Value result = {.type = VAL_BOOL, .data.bool_val = found};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_REPLACE: {
                Value new_str = pop(vm);
                Value old_str = pop(vm);
                Value str = pop(vm);
                const char* s = str.data.string_val;
                const char* old = old_str.data.string_val;
                const char* new = new_str.data.string_val;
                
                size_t old_len = strlen(old);
                size_t new_len = strlen(new);
                
                if (old_len == 0) {
                    // Cannot replace empty string, return original
                    Value result = {.type = VAL_STRING, .data.string_val = strdup(s)};
                    free(str.data.string_val);
                    free(old_str.data.string_val);
                    free(new_str.data.string_val);
                    push(vm, result);
                    vm->ip++;
                    break;
                }
                
                // Count occurrences
                int count = 0;
                const char* p = s;
                while ((p = strstr(p, old)) != NULL) {
                    count++;
                    p += old_len;
                }
                
                // Allocate result buffer
                size_t result_len = strlen(s) + count * (new_len - old_len);
                char* result_str = malloc(result_len + 1);
                char* dst = result_str;
                const char* src = s;
                
                // Perform replacements
                const char* found;
                while ((found = strstr(src, old)) != NULL) {
                    size_t len = found - src;
                    memcpy(dst, src, len);
                    dst += len;
                    memcpy(dst, new, new_len);
                    dst += new_len;
                    src = found + old_len;
                }
                // Copy remaining
                strcpy(dst, src);
                
                free(str.data.string_val);
                free(old_str.data.string_val);
                free(new_str.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = result_str};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_STARTS_WITH: {
                Value suffix_val = pop(vm);
                Value str_val = pop(vm);
                char* str = str_val.data.string_val;
                char* prefix = suffix_val.data.string_val;
                
                size_t str_len = strlen(str);
                size_t prefix_len = strlen(prefix);
                
                bool result = false;
                if (prefix_len <= str_len) {
                    result = (strncmp(str, prefix, prefix_len) == 0);
                }
                
                free(str_val.data.string_val);
                free(suffix_val.data.string_val);
                Value bool_result = {.type = VAL_BOOL, .data.bool_val = result};
                push(vm, bool_result);
                vm->ip++;
                break;
            }

            case OP_STR_ENDS_WITH: {
                Value suffix_val = pop(vm);
                Value str_val = pop(vm);
                char* str = str_val.data.string_val;
                char* suffix = suffix_val.data.string_val;
                
                size_t str_len = strlen(str);
                size_t suffix_len = strlen(suffix);
                
                bool result = false;
                if (suffix_len <= str_len) {
                    result = (strcmp(str + str_len - suffix_len, suffix) == 0);
                }
                
                free(str_val.data.string_val);
                free(suffix_val.data.string_val);
                Value bool_result = {.type = VAL_BOOL, .data.bool_val = result};
                push(vm, bool_result);
                vm->ip++;
                break;
            }

            case OP_STR_TO_UPPER: {
                Value str_val = pop(vm);
                char* str = str_val.data.string_val;
                size_t len = strlen(str);
                
                char* result_str = malloc(len + 1);
                for (size_t i = 0; i < len; i++) {
                    result_str[i] = toupper((unsigned char)str[i]);
                }
                result_str[len] = '\0';
                
                free(str_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = result_str};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_STR_TO_LOWER: {
                Value str_val = pop(vm);
                char* str = str_val.data.string_val;
                size_t len = strlen(str);
                
                char* result_str = malloc(len + 1);
                for (size_t i = 0; i < len; i++) {
                    result_str[i] = tolower((unsigned char)str[i]);
                }
                result_str[len] = '\0';
                
                free(str_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = result_str};
                push(vm, result);
                vm->ip++;
                break;
            }

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

            // ============================================
            // MAP OPERATIONS
            // ============================================

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

            // ============================================
            // JSON OPERATIONS
            // ============================================

            case OP_JSON_PARSE: {
                Value str_val = pop(vm);
                const char* json_str = str_val.data.string_val;
                JsonValue* json = json_parse(json_str);
                free(str_val.data.string_val);
                
                if (!json) {
                    // Parse error - return null JSON
                    json = json_new(JSON_NULL);
                }
                
                Value result = {.type = VAL_JSON, .data.ptr_val = json};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_JSON_STRINGIFY: {
                Value json_val = pop(vm);
                JsonValue* json = (JsonValue*)json_val.data.ptr_val;
                char* json_str = json_stringify(json);
                Value result = {.type = VAL_STRING, .data.string_val = json_str};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_JSON_NEW_OBJECT: {
                JsonValue* json = json_new(JSON_OBJECT);
                Value result = {.type = VAL_JSON, .data.ptr_val = json};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_JSON_NEW_ARRAY: {
                JsonValue* json = json_new(JSON_ARRAY);
                Value result = {.type = VAL_JSON, .data.ptr_val = json};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_JSON_GET: {
                Value key_val = pop(vm);
                Value json_val = pop(vm);
                JsonValue* json = (JsonValue*)json_val.data.ptr_val;
                
                JsonValue* result_json = NULL;
                if (json->type == JSON_OBJECT && key_val.type == VAL_STRING) {
                    result_json = json_object_get(json, key_val.data.string_val);
                    free(key_val.data.string_val);
                } else if (json->type == JSON_ARRAY && key_val.type == VAL_I32) {
                    result_json = json_array_get(json, (uint32_t)key_val.data.i32_val);
                }
                
                // Convert JSON value to AISL Value
                Value result = {.type = VAL_UNIT};
                if (result_json) {
                    switch (result_json->type) {
                        case JSON_NULL:
                            result.type = VAL_UNIT;
                            break;
                        case JSON_BOOL:
                            result.type = VAL_BOOL;
                            result.data.bool_val = result_json->data.bool_val;
                            break;
                        case JSON_NUMBER: {
                            double num = result_json->data.number_val;
                            // If it's a whole number, return as I32
                            if (num == (int32_t)num && num >= INT32_MIN && num <= INT32_MAX) {
                                result.type = VAL_I32;
                                result.data.i32_val = (int32_t)num;
                            } else {
                                result.type = VAL_F64;
                                result.data.f64_val = num;
                            }
                            break;
                        }
                        case JSON_STRING:
                            result.type = VAL_STRING;
                            result.data.string_val = strdup(result_json->data.string_val);
                            break;
                        case JSON_ARRAY:
                        case JSON_OBJECT:
                            result.type = VAL_JSON;
                            result.data.ptr_val = result_json;
                            break;
                    }
                }
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_JSON_SET: {
                Value val = pop(vm);
                Value key_val = pop(vm);
                Value json_val = pop(vm);
                JsonValue* json = (JsonValue*)json_val.data.ptr_val;
                
                JsonValue* json_value = NULL;
                switch (val.type) {
                    case VAL_UNIT:
                        json_value = json_new(JSON_NULL);
                        break;
                    case VAL_BOOL:
                        json_value = json_new(JSON_BOOL);
                        json_value->data.bool_val = val.data.bool_val;
                        break;
                    case VAL_INT:
                    case VAL_I8:
                    case VAL_I16:
                    case VAL_I32:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = (double)val.data.i32_val;
                        break;
                    case VAL_I64:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = (double)val.data.i64_val;
                        break;
                    case VAL_F32:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = (double)val.data.f32_val;
                        break;
                    case VAL_F64:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = val.data.f64_val;
                        break;
                    case VAL_STRING:
                        json_value = json_new(JSON_STRING);
                        json_value->data.string_val = val.data.string_val;
                        break;
                    case VAL_JSON:
                        json_value = (JsonValue*)val.data.ptr_val;
                        break;
                    default:
                        json_value = json_new(JSON_NULL);
                        break;
                }
                
                if (json->type == JSON_OBJECT && key_val.type == VAL_STRING) {
                    json_object_set(json, key_val.data.string_val, json_value);
                    free(key_val.data.string_val);
                }
                
                push(vm, json_val);
                vm->ip++;
                break;
            }

            case OP_JSON_PUSH: {
                Value val = pop(vm);
                Value json_val = pop(vm);
                JsonValue* json = (JsonValue*)json_val.data.ptr_val;
                
                JsonValue* json_value = NULL;
                switch (val.type) {
                    case VAL_INT:
                    case VAL_I8:
                    case VAL_I16:
                    case VAL_I32:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = (double)val.data.i32_val;
                        break;
                    case VAL_I64:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = (double)val.data.i64_val;
                        break;
                    case VAL_F32:
                    case VAL_F64:
                        json_value = json_new(JSON_NUMBER);
                        json_value->data.number_val = val.data.f64_val;
                        break;
                    case VAL_STRING:
                        json_value = json_new(JSON_STRING);
                        json_value->data.string_val = val.data.string_val;
                        break;
                    case VAL_BOOL:
                        json_value = json_new(JSON_BOOL);
                        json_value->data.bool_val = val.data.bool_val;
                        break;
                    case VAL_JSON:
                        json_value = (JsonValue*)val.data.ptr_val;
                        break;
                    default:
                        json_value = json_new(JSON_NULL);
                        break;
                }
                
                if (json->type == JSON_ARRAY) {
                    json_array_push(json, json_value);
                }
                
                push(vm, json_val);
                vm->ip++;
                break;
            }

            case OP_JSON_LENGTH: {
                Value json_val = pop(vm);
                JsonValue* json = (JsonValue*)json_val.data.ptr_val;
                Value result = {.type = VAL_I32, .data.i32_val = (int32_t)json->length};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_JSON_TYPE: {
                Value json_val = pop(vm);
                JsonValue* json = (JsonValue*)json_val.data.ptr_val;
                const char* type_str = "unknown";
                switch (json->type) {
                    case JSON_NULL: type_str = "null"; break;
                    case JSON_BOOL: type_str = "bool"; break;
                    case JSON_NUMBER: type_str = "number"; break;
                    case JSON_STRING: type_str = "string"; break;
                    case JSON_ARRAY: type_str = "array"; break;
                    case JSON_OBJECT: type_str = "object"; break;
                }
                Value result = {.type = VAL_STRING, .data.string_val = strdup(type_str)};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_HTTP_GET: {
                Value url_val = pop(vm);
                HttpResponse* resp = http_get(url_val.data.string_val);
                free(url_val.data.string_val);
                Value result = {.type = VAL_HTTP_RESPONSE, .data.ptr_val = resp};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_HTTP_GET_STATUS: {
                Value resp_val = pop(vm);
                HttpResponse* resp = (HttpResponse*)resp_val.data.ptr_val;
                Value result = {.type = VAL_I32, .data.i32_val = resp->status_code};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_HTTP_GET_BODY: {
                Value resp_val = pop(vm);
                HttpResponse* resp = (HttpResponse*)resp_val.data.ptr_val;
                char* body = resp->body ? strdup(resp->body) : strdup("");
                Value result = {.type = VAL_STRING, .data.string_val = body};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_HTTP_POST: {
                Value body_val = pop(vm);
                Value url_val = pop(vm);
                HttpResponse* resp = http_post(url_val.data.string_val, body_val.data.string_val);
                free(url_val.data.string_val);
                free(body_val.data.string_val);
                Value result = {.type = VAL_HTTP_RESPONSE, .data.ptr_val = resp};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_HTTP_PUT: {
                Value body_val = pop(vm);
                Value url_val = pop(vm);
                HttpResponse* resp = http_put(url_val.data.string_val, body_val.data.string_val);
                free(url_val.data.string_val);
                free(body_val.data.string_val);
                Value result = {.type = VAL_HTTP_RESPONSE, .data.ptr_val = resp};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_HTTP_DELETE: {
                Value url_val = pop(vm);
                HttpResponse* resp = http_delete(url_val.data.string_val);
                free(url_val.data.string_val);
                Value result = {.type = VAL_HTTP_RESPONSE, .data.ptr_val = resp};
                push(vm, result);
                vm->ip++;
                break;
            }

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

            case OP_BASE64_ENCODE: {
                Value input_val = pop(vm);
                char* encoded = base64_encode(input_val.data.string_val);
                free(input_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = encoded};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_BASE64_DECODE: {
                Value input_val = pop(vm);
                char* decoded = base64_decode(input_val.data.string_val);
                free(input_val.data.string_val);
                Value result = {.type = VAL_STRING, .data.string_val = decoded};
                push(vm, result);
                vm->ip++;
                break;
            }

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

            // ============================================
            // TYPE CONVERSION OPERATIONS (v6.0 - int/float only)
            // ============================================

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

            // ============================================
            // MATH OPERATIONS
            // ============================================

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

            // ============================================
            // SQLITE DATABASE OPERATIONS
            // ============================================

            case OP_SQLITE_OPEN: {
                Value path_val = pop(vm);
                SqliteDB* db = sqlite_open(path_val.data.string_val);
                free(path_val.data.string_val);
                Value result = {.type = VAL_SQLITE_DB, .data.ptr_val = db};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_SQLITE_CLOSE: {
                Value db_val = pop(vm);
                SqliteDB* db = (SqliteDB*)db_val.data.ptr_val;
                sqlite_close(db);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            case OP_SQLITE_EXEC: {
                Value sql_val = pop(vm);
                Value db_val = pop(vm);
                SqliteDB* db = (SqliteDB*)db_val.data.ptr_val;
                int result = sqlite_exec(db, sql_val.data.string_val);
                free(sql_val.data.string_val);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_SQLITE_QUERY: {
                Value sql_val = pop(vm);
                Value db_val = pop(vm);
                SqliteDB* db = (SqliteDB*)db_val.data.ptr_val;
                Array* results = sqlite_query(db, sql_val.data.string_val);
                free(sql_val.data.string_val);
                Value result_val = {.type = VAL_ARRAY, .data.ptr_val = results};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_SQLITE_PREPARE: {
                Value sql_val = pop(vm);
                Value db_val = pop(vm);
                SqliteDB* db = (SqliteDB*)db_val.data.ptr_val;
                SqliteStmt* stmt = sqlite_prepare(db, sql_val.data.string_val);
                free(sql_val.data.string_val);
                Value result = {.type = VAL_SQLITE_STMT, .data.ptr_val = stmt};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_SQLITE_BIND: {
#ifdef HAVE_SQLITE3
                Value value_val = pop(vm);
                Value index_val = pop(vm);
                Value stmt_val = pop(vm);
                SqliteStmt* stmt = (SqliteStmt*)stmt_val.data.ptr_val;
                
                int index = index_val.data.i32_val;
                switch (value_val.type) {
                    case VAL_I32:
                        sqlite3_bind_int(stmt->stmt, index, value_val.data.i32_val);
                        break;
                    case VAL_I64:
                        sqlite3_bind_int64(stmt->stmt, index, value_val.data.i64_val);
                        break;
                    case VAL_F64:
                        sqlite3_bind_double(stmt->stmt, index, value_val.data.f64_val);
                        break;
                    case VAL_STRING:
                        sqlite3_bind_text(stmt->stmt, index, value_val.data.string_val, -1, SQLITE_TRANSIENT);
                        free(value_val.data.string_val);
                        break;
                    default:
                        sqlite3_bind_null(stmt->stmt, index);
                        break;
                }
                
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
#else
                pop(vm); pop(vm); pop(vm);
                fprintf(stderr, "SQLite support not compiled in\n");
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
#endif
                vm->ip++;
                break;
            }

            case OP_SQLITE_STEP: {
#ifdef HAVE_SQLITE3
                Value stmt_val = pop(vm);
                SqliteStmt* stmt = (SqliteStmt*)stmt_val.data.ptr_val;
                int result = sqlite3_step(stmt->stmt);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
#else
                pop(vm);
                fprintf(stderr, "SQLite support not compiled in\n");
                Value result = {.type = VAL_I32, .data.i32_val = 0};
                push(vm, result);
#endif
                vm->ip++;
                break;
            }

            case OP_SQLITE_COLUMN: {
#ifdef HAVE_SQLITE3
                Value index_val = pop(vm);
                Value stmt_val = pop(vm);
                SqliteStmt* stmt = (SqliteStmt*)stmt_val.data.ptr_val;
                int index = index_val.data.i32_val;
                
                int col_type = sqlite3_column_type(stmt->stmt, index);
                Value result;
                
                switch (col_type) {
                    case SQLITE_INTEGER:
                        result.type = VAL_I64;
                        result.data.i64_val = sqlite3_column_int64(stmt->stmt, index);
                        break;
                    case SQLITE_FLOAT:
                        result.type = VAL_F64;
                        result.data.f64_val = sqlite3_column_double(stmt->stmt, index);
                        break;
                    case SQLITE_TEXT:
                        result.type = VAL_STRING;
                        result.data.string_val = strdup((const char*)sqlite3_column_text(stmt->stmt, index));
                        break;
                    case SQLITE_NULL:
                    default:
                        result.type = VAL_UNIT;
                        break;
                }
                
                push(vm, result);
#else
                pop(vm); pop(vm);
                fprintf(stderr, "SQLite support not compiled in\n");
                Value result = {.type = VAL_UNIT};
                push(vm, result);
#endif
                vm->ip++;
                break;
            }

            case OP_SQLITE_RESET: {
#ifdef HAVE_SQLITE3
                Value stmt_val = pop(vm);
                SqliteStmt* stmt = (SqliteStmt*)stmt_val.data.ptr_val;
                sqlite3_reset(stmt->stmt);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
#else
                pop(vm);
                fprintf(stderr, "SQLite support not compiled in\n");
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
#endif
                vm->ip++;
                break;
            }

            case OP_SQLITE_FINALIZE: {
#ifdef HAVE_SQLITE3
                Value stmt_val = pop(vm);
                SqliteStmt* stmt = (SqliteStmt*)stmt_val.data.ptr_val;
                sqlite3_finalize(stmt->stmt);
                free(stmt);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
#else
                pop(vm);
                fprintf(stderr, "SQLite support not compiled in\n");
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
#endif
                vm->ip++;
                break;
            }

            // ============================================
            // WEBSOCKET OPERATIONS
            // ============================================

            case OP_WS_CONNECT: {
                Value url_val = pop(vm);
                WebSocket* ws = ws_connect(url_val.data.string_val);
                free(url_val.data.string_val);
                Value result = {.type = VAL_WEBSOCKET, .data.ptr_val = ws};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_WS_SEND: {
                Value message_val = pop(vm);
                Value ws_val = pop(vm);
                WebSocket* ws = (WebSocket*)ws_val.data.ptr_val;
                int result = ws_send(ws, message_val.data.string_val);
                free(message_val.data.string_val);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_WS_RECEIVE: {
                Value ws_val = pop(vm);
                WebSocket* ws = (WebSocket*)ws_val.data.ptr_val;
                char* message = ws_receive(ws);
                Value result = {.type = VAL_STRING, .data.string_val = message};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_WS_CLOSE: {
                Value ws_val = pop(vm);
                WebSocket* ws = (WebSocket*)ws_val.data.ptr_val;
                ws_close(ws);
                Value unit = {.type = VAL_UNIT};
                push(vm, unit);
                vm->ip++;
                break;
            }

            // ============================================
            // PROCESS MANAGEMENT OPERATIONS
            // ============================================

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
                
                execvp(cmd_val.data.string_val, (char* const*)args);
                
                // If exec returns, it failed
                fprintf(stderr, "execvp failed: %s\n", strerror(errno));
                exit(1);
                break;
            }

            case OP_PROCESS_WAIT: {
                Value proc_val = pop(vm);
                Process* proc = (Process*)proc_val.data.ptr_val;
                int exit_code = process_wait(proc);
                Value result = {.type = VAL_I32, .data.i32_val = exit_code};
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
                Process* proc = (Process*)proc_val.data.ptr_val;
                char* output = process_read(proc);
                Value result = {.type = VAL_STRING, .data.string_val = output};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_PROCESS_WRITE: {
                Value data_val = pop(vm);
                Value proc_val = pop(vm);
                Process* proc = (Process*)proc_val.data.ptr_val;
                int result = process_write(proc, data_val.data.string_val);
                free(data_val.data.string_val);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            // ============================================
            // NETWORK SOCKET OPERATIONS
            // ============================================

            case OP_TCP_LISTEN: {
                Value port_val = pop(vm);
                int port = port_val.data.i32_val;
                Socket* sock = tcp_listen(port);
                Value result = {.type = VAL_TCP_SOCKET, .data.ptr_val = sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_ACCEPT: {
                Value sock_val = pop(vm);
                Socket* server_sock = (Socket*)sock_val.data.ptr_val;
                Socket* client_sock = tcp_accept(server_sock);
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
                Value result = {.type = VAL_TCP_SOCKET, .data.ptr_val = sock};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_SEND: {
                Value data_val = pop(vm);
                Value sock_val = pop(vm);
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                int result = tcp_send(sock, data_val.data.string_val);
                free(data_val.data.string_val);
                Value result_val = {.type = VAL_I32, .data.i32_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_TCP_RECEIVE: {
                Value max_bytes_val = pop(vm);
                Value sock_val = pop(vm);
                Socket* sock = (Socket*)sock_val.data.ptr_val;
                int max_bytes = max_bytes_val.data.i32_val;
                char* data = tcp_receive(sock, max_bytes);
                Value result = {.type = VAL_STRING, .data.string_val = data};
                push(vm, result);
                vm->ip++;
                break;
            }

            case OP_TCP_CLOSE: {
                Value sock_val = pop(vm);
                Socket* sock = (Socket*)sock_val.data.ptr_val;
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

            // ============================================
            // GARBAGE COLLECTION OPERATIONS
            // ============================================

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

            // ============================================
            // RESULT TYPE OPERATIONS
            // ============================================

            case OP_RESULT_OK: {
                // Create Ok result from stack value
                Value val = pop(vm);
                Result* result = malloc(sizeof(Result));
                result->is_ok = true;
                result->data.ok_value = val;
                
                Value result_val = {.type = VAL_RESULT, .data.ptr_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_RESULT_ERR: {
                // Create Err result from error code and message
                Value msg_val = pop(vm);
                Value code_val = pop(vm);
                
                Result* result = malloc(sizeof(Result));
                result->is_ok = false;
                result->data.err.code = code_val.data.i32_val;
                result->data.err.message = msg_val.data.string_val;
                
                Value result_val = {.type = VAL_RESULT, .data.ptr_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_RESULT_IS_OK: {
                // Check if result is Ok
                Value result_val = pop(vm);
                Result* result = (Result*)result_val.data.ptr_val;
                
                Value is_ok = {.type = VAL_BOOL, .data.bool_val = result->is_ok};
                push(vm, is_ok);
                vm->ip++;
                break;
            }

            case OP_RESULT_IS_ERR: {
                // Check if result is Err
                Value result_val = pop(vm);
                Result* result = (Result*)result_val.data.ptr_val;
                
                Value is_err = {.type = VAL_BOOL, .data.bool_val = !result->is_ok};
                push(vm, is_err);
                vm->ip++;
                break;
            }

            case OP_RESULT_UNWRAP: {
                // Extract value from Ok, panic on Err
                Value result_val = pop(vm);
                Result* result = (Result*)result_val.data.ptr_val;
                
                if (!result->is_ok) {
                    fprintf(stderr, "Runtime error: unwrap called on Err result\n");
                    fprintf(stderr, "Error code: %d\n", result->data.err.code);
                    fprintf(stderr, "Error message: %s\n", result->data.err.message);
                    return 1;
                }
                
                push(vm, result->data.ok_value);
                vm->ip++;
                break;
            }

            case OP_RESULT_UNWRAP_OR: {
                // Extract value or return default
                Value default_val = pop(vm);
                Value result_val = pop(vm);
                Result* result = (Result*)result_val.data.ptr_val;
                
                if (result->is_ok) {
                    push(vm, result->data.ok_value);
                } else {
                    push(vm, default_val);
                }
                vm->ip++;
                break;
            }

            case OP_RESULT_ERROR_CODE: {
                // Get error code from Err
                Value result_val = pop(vm);
                Result* result = (Result*)result_val.data.ptr_val;
                
                if (result->is_ok) {
                    fprintf(stderr, "Runtime error: error_code called on Ok result\n");
                    return 1;
                }
                
                Value code = {.type = VAL_I32, .data.i32_val = result->data.err.code};
                push(vm, code);
                vm->ip++;
                break;
            }

            case OP_RESULT_ERROR_MSG: {
                // Get error message from Err
                Value result_val = pop(vm);
                Result* result = (Result*)result_val.data.ptr_val;
                
                if (result->is_ok) {
                    fprintf(stderr, "Runtime error: error_message called on Ok result\n");
                    return 1;
                }
                
                Value msg = {.type = VAL_STRING, .data.string_val = strdup(result->data.err.message)};
                push(vm, msg);
                vm->ip++;
                break;
            }

            case OP_FILE_READ_RESULT: {
                // Read file with error handling
                Value path_val = pop(vm);
                char* content = file_read(path_val.data.string_val);
                
                Result* result = malloc(sizeof(Result));
                if (content) {
                    // Success - create Ok result
                    result->is_ok = true;
                    result->data.ok_value.type = VAL_STRING;
                    result->data.ok_value.data.string_val = content;
                } else {
                    // Error - create Err result
                    result->is_ok = false;
                    result->data.err.code = -1;
                    char* err_msg = malloc(256);
                    snprintf(err_msg, 256, "Failed to read file: %s", path_val.data.string_val);
                    result->data.err.message = err_msg;
                }
                
                free(path_val.data.string_val);
                Value result_val = {.type = VAL_RESULT, .data.ptr_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_FILE_WRITE_RESULT: {
                // Write file with error handling
                Value content_val = pop(vm);
                Value path_val = pop(vm);
                int success = file_write(path_val.data.string_val, content_val.data.string_val);
                
                Result* result = malloc(sizeof(Result));
                if (success) {
                    // Success - create Ok result with unit
                    result->is_ok = true;
                    result->data.ok_value.type = VAL_UNIT;
                } else {
                    // Error - create Err result
                    result->is_ok = false;
                    result->data.err.code = -1;
                    char* err_msg = malloc(256);
                    snprintf(err_msg, 256, "Failed to write file: %s", path_val.data.string_val);
                    result->data.err.message = err_msg;
                }
                
                free(path_val.data.string_val);
                free(content_val.data.string_val);
                Value result_val = {.type = VAL_RESULT, .data.ptr_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            case OP_FILE_APPEND_RESULT: {
                // Append to file with error handling
                Value content_val = pop(vm);
                Value path_val = pop(vm);
                int success = file_append(path_val.data.string_val, content_val.data.string_val);
                
                Result* result = malloc(sizeof(Result));
                if (success) {
                    // Success - create Ok result with unit
                    result->is_ok = true;
                    result->data.ok_value.type = VAL_UNIT;
                } else {
                    // Error - create Err result
                    result->is_ok = false;
                    result->data.err.code = -1;
                    char* err_msg = malloc(256);
                    snprintf(err_msg, 256, "Failed to append to file: %s", path_val.data.string_val);
                    result->data.err.message = err_msg;
                }
                
                free(path_val.data.string_val);
                free(content_val.data.string_val);
                Value result_val = {.type = VAL_RESULT, .data.ptr_val = result};
                push(vm, result_val);
                vm->ip++;
                break;
            }

            // ============================================
            // FFI (FOREIGN FUNCTION INTERFACE) OPERATIONS
            // ============================================
            
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

// ============================================
// DISASSEMBLER
// ============================================

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
            case OP_STR_SPLIT:
                printf("STR_SPLIT\n");
                break;
            case OP_STR_TRIM:
                printf("STR_TRIM\n");
                break;
            case OP_STR_CONTAINS:
                printf("STR_CONTAINS\n");
                break;
            case OP_STR_REPLACE:
                printf("STR_REPLACE\n");
                break;
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
