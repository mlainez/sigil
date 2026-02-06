#ifndef TEST_RUNNER_H
#define TEST_RUNNER_H

#include "test_framework.h"
#include "vm.h"
#include "bytecode.h"
#include "ast.h"

TestSpecList* extract_test_specs(Module* mod);
Definition* find_function(Module* mod, const char* name);
TestResult run_test_case(VM* vm, TestCase* test, Definition* target_func, BytecodeProgram* program);
TestResults* run_test_spec(VM* vm, TestSpec* spec, Module* mod, BytecodeProgram* program);
void print_test_results(TestResults* results, const char* module_name);
void run_all_tests(Module* mod, BytecodeProgram* program);

#endif
