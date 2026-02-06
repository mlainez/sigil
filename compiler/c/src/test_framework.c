#define _POSIX_C_SOURCE 200809L
#include "test_framework.h"
#include <stdlib.h>
#include <string.h>

TestSpec* test_spec_new(TestKind kind, const char* target, int line) {
    TestSpec* spec = malloc(sizeof(TestSpec));
    spec->kind = kind;
    spec->target_function = strdup(target);
    spec->line = line;
    spec->data.test_cases = NULL;
    return spec;
}

TestCase* test_case_new(const char* desc, ExprList* inputs, Expr* expected, int line) {
    TestCase* tc = malloc(sizeof(TestCase));
    tc->description = strdup(desc);
    tc->input_args = inputs;
    tc->expected = expected;
    tc->mocks = NULL;
    tc->line = line;
    return tc;
}

MockSpec* mock_spec_new(const char* func_name, ExprList* args, Expr* ret_val) {
    MockSpec* mock = malloc(sizeof(MockSpec));
    mock->function_name = strdup(func_name);
    mock->input_args = args;
    mock->return_value = ret_val;
    mock->call_sequence = 0;
    return mock;
}

PropertyTest* property_test_new(const char* desc, ParamList* vars, Expr* constraint, Expr* assertion) {
    PropertyTest* prop = malloc(sizeof(PropertyTest));
    prop->description = strdup(desc);
    prop->forall_vars = vars;
    prop->constraint = constraint;
    prop->assertion = assertion;
    prop->num_cases = 100;
    return prop;
}

TestCaseList* test_case_list_new(TestCase* tc, TestCaseList* next) {
    TestCaseList* list = malloc(sizeof(TestCaseList));
    list->test_case = tc;
    list->next = next;
    return list;
}

TestSpecList* test_spec_list_new(TestSpec* spec, TestSpecList* next) {
    TestSpecList* list = malloc(sizeof(TestSpecList));
    list->spec = spec;
    list->next = next;
    return list;
}

MockSpecList* mock_spec_list_new(MockSpec* mock, MockSpecList* next) {
    MockSpecList* list = malloc(sizeof(MockSpecList));
    list->mock = mock;
    list->next = next;
    return list;
}

PropertyTestList* property_test_list_new(PropertyTest* prop, PropertyTestList* next) {
    PropertyTestList* list = malloc(sizeof(PropertyTestList));
    list->property = prop;
    list->next = next;
    return list;
}

void free_test_spec(TestSpec* spec) {
    if (!spec) return;
    
    free(spec->target_function);
    
    if (spec->kind == TEST_CASE && spec->data.test_cases) {
        TestCaseList* current = spec->data.test_cases;
        while (current) {
            TestCaseList* next = current->next;
            if (current->test_case) {
                free(current->test_case->description);
                free(current->test_case);
            }
            free(current);
            current = next;
        }
    }
    
    free(spec);
}

void free_test_results(TestResults* results) {
    if (!results) return;
    
    for (int i = 0; i < results->total; i++) {
        free(results->results[i].test_name);
        free(results->results[i].expected_str);
        free(results->results[i].actual_str);
        free(results->results[i].error_message);
    }
    
    free(results->results);
    free(results);
}
