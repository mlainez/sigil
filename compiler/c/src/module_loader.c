// Add feature test macro for strdup
#define _POSIX_C_SOURCE 200809L

#include "module_loader.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>
#include <pwd.h>

// Module search paths in priority order
static const char* SEARCH_PATHS[MODULE_SEARCH_PATH_COUNT] = {
    "./stdlib",               // Project stdlib (pure AISL)
    "./modules",              // Project-local modules
    NULL,                     // ~/.aisl/modules (set at runtime)
    "/usr/lib/aisl/modules"   // System stdlib
};

// Get user home directory
static char* get_home_dir(void) {
    const char* home = getenv("HOME");
    if (home) return strdup(home);
    
    struct passwd* pw = getpwuid(getuid());
    if (pw) return strdup(pw->pw_dir);
    
    return NULL;
}

// Initialize search paths (sets up ~/.aisl/modules)
static void init_search_paths(void) {
    static bool initialized = false;
    if (initialized) return;
    
    char* home = get_home_dir();
    if (home) {
        char* user_path = malloc(strlen(home) + 20);
        sprintf(user_path, "%s/.aisl/modules", home);
        SEARCH_PATHS[2] = user_path;
        free(home);
    }
    
    initialized = true;
}

// Check if file exists
static bool file_exists(const char* path) {
    struct stat st;
    return stat(path, &st) == 0;
}

// Resolve module name to file path
char* module_resolve_path(const char* module_name) {
    init_search_paths();
    
    for (int i = 0; i < MODULE_SEARCH_PATH_COUNT; i++) {
        if (!SEARCH_PATHS[i]) continue;
        
        // Try <search_path>/<module_name>.aisl
        char* path = malloc(strlen(SEARCH_PATHS[i]) + strlen(module_name) + 10);
        sprintf(path, "%s/%s.aisl", SEARCH_PATHS[i], module_name);
        
        if (file_exists(path)) {
            return path;
        }
        
        free(path);
        
        // For stdlib, also search in subdirectories (core, data, net, sys, crypto, db, pattern)
        if (strstr(SEARCH_PATHS[i], "stdlib")) {
            const char* subdirs[] = {"core", "data", "net", "sys", "crypto", "db", "pattern", NULL};
            for (int j = 0; subdirs[j] != NULL; j++) {
                char* subpath = malloc(strlen(SEARCH_PATHS[i]) + strlen(subdirs[j]) + strlen(module_name) + 20);
                sprintf(subpath, "%s/%s/%s.aisl", SEARCH_PATHS[i], subdirs[j], module_name);
                
                if (file_exists(subpath)) {
                    return subpath;
                }
                
                free(subpath);
            }
        }
    }
    
    return NULL;  // Not found
}

// Get search paths
const char** module_get_search_paths(void) {
    init_search_paths();
    return SEARCH_PATHS;
}

// Create new module cache
ModuleCache* module_cache_new(void) {
    ModuleCache* cache = malloc(sizeof(ModuleCache));
    cache->modules = NULL;
    cache->count = 0;
    cache->capacity = 0;
    return cache;
}

// Free module cache
void module_cache_free(ModuleCache* cache) {
    if (!cache) return;
    
    for (int i = 0; i < cache->count; i++) {
        LoadedModule* mod = cache->modules[i];
        free(mod->module_name);
        free(mod->module_path);
        if (mod->manifest_path) free(mod->manifest_path);
        if (mod->source) free(mod->source);  // Free source buffer
        // Note: parsed_module is freed by AST cleanup
        free(mod);
    }
    
    free(cache->modules);
    free(cache);
}

// Get module from cache
LoadedModule* module_cache_get(ModuleCache* cache, const char* module_name) {
    for (int i = 0; i < cache->count; i++) {
        if (strcmp(cache->modules[i]->module_name, module_name) == 0) {
            return cache->modules[i];
        }
    }
    return NULL;
}

// Add module to cache
static void module_cache_add(ModuleCache* cache, LoadedModule* module) {
    if (cache->count >= cache->capacity) {
        cache->capacity = cache->capacity == 0 ? 8 : cache->capacity * 2;
        cache->modules = realloc(cache->modules, 
                                 sizeof(LoadedModule*) * cache->capacity);
    }
    cache->modules[cache->count++] = module;
}

// Load module by name
LoadedModule* module_load(ModuleCache* cache, const char* module_name) {
    // Check if already loaded
    LoadedModule* cached = module_cache_get(cache, module_name);
    if (cached) return cached;
    
    // Resolve path
    char* module_path = module_resolve_path(module_name);
    if (!module_path) {
        fprintf(stderr, "Error: Module '%s' not found\n", module_name);
        fprintf(stderr, "\nSearched in:\n");
        const char** paths = module_get_search_paths();
        for (int i = 0; i < MODULE_SEARCH_PATH_COUNT; i++) {
            if (paths[i]) {
                fprintf(stderr, "  - %s/%s.aisl\n", paths[i], module_name);
            }
        }
        fprintf(stderr, "\nCommon issues:\n");
        fprintf(stderr, "  1. Module file doesn't exist\n");
        fprintf(stderr, "  2. Module name conflicts with type keyword (json, array, map, string, etc.)\n");
        fprintf(stderr, "  3. Module uses 'mod' instead of 'module' keyword\n");
        fprintf(stderr, "  4. Check spelling and capitalization\n");
        return NULL;
    }
    
    // Create loaded module entry
    LoadedModule* module = malloc(sizeof(LoadedModule));
    module->module_name = strdup(module_name);
    module->module_path = module_path;
    module->parsed_module = NULL;
    module->source = NULL;  // Will be set when compiling
    
    // Check for manifest
    module->manifest_path = malloc(strlen(module_path) + 10);
    sprintf(module->manifest_path, "%s.manifest", module_path);
    module->has_manifest = file_exists(module->manifest_path);
    
    if (!module->has_manifest) {
        free(module->manifest_path);
        module->manifest_path = NULL;
    }
    
    // Add to cache
    module_cache_add(cache, module);
    
    // Note: Actual parsing/compilation happens in compiler.c
    // This just tracks the module location
    
    return module;
}
