#include "bytecode.h"
#include "vm.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <program.aislc> [--disasm]\n", argv[0]);
        return 1;
    }

    const char* filename = argv[1];
    bool disassemble = false;

    if (argc > 2 && strcmp(argv[2], "--disasm") == 0) {
        disassemble = true;
    }

    // Load bytecode
    BytecodeProgram* program = bytecode_load(filename);
    if (!program) {
        return 1;
    }

    if (disassemble) {
        vm_disassemble(program);
        bytecode_program_free(program);
        return 0;
    }

    // Create VM and run
    VM* vm = vm_new(program);
    int exit_code = vm_run(vm);

    vm_free(vm);
    bytecode_program_free(program);

    return exit_code;
}
