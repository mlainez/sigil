#ifndef MODULE_LOADER_H
#define MODULE_LOADER_H

#include <stdbool.h>

// Module search paths (priority order)
#define MODULE_SEARCH_PATH_COUNT 4

typedef struct {
    char* module_name;           // e.g. "math"
    char* module_path;           // Full path to .aisl file
    char* manifest_path;         // Full path to .aisl.manifest
    bool has_manifest;           // Whether manifest exists
    void* parsed_module;         // Module* after compilation
    char* source;                // Source code buffer (kept alive for AST)
} LoadedModule;

typedef struct {
    LoadedModule** modules;      // Array of loaded modules
    int count;                   // Number of loaded modules
    int capacity;                // Allocated capacity
} ModuleCache;

// Initialize module cache
ModuleCache* module_cache_new(void);

// Free module cache
void module_cache_free(ModuleCache* cache);

// Resolve module name to file path
// Returns NULL if not found in any search path
char* module_resolve_path(const char* module_name);

// Load module by name (searches paths, parses, compiles)
// Returns LoadedModule* or NULL if not found/error
LoadedModule* module_load(ModuleCache* cache, const char* module_name);

// Check if module is already loaded
LoadedModule* module_cache_get(ModuleCache* cache, const char* module_name);

// Get search paths for module resolution
const char** module_get_search_paths(void);

#endif // MODULE_LOADER_H
