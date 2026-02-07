// Simple FFI test extension for AISL
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

// Simple function that returns a constant
int64_t hello_aisl() {
    return 42;
}

// Function that adds two numbers
int64_t add_numbers_aisl(int64_t a, int64_t b) {
    return a + b;
}

// Function that returns a greeting
const char* get_greeting_aisl(const char* name) {
    static char buffer[256];
    snprintf(buffer, sizeof(buffer), "Hello, %s!", name);
    return buffer;
}

// Function that concatenates two strings
const char* concat_strings_aisl(const char* a, const char* b) {
    static char buffer[512];
    snprintf(buffer, sizeof(buffer), "%s%s", a, b);
    return buffer;
}
