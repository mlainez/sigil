#ifndef TEST_FRAMEWORK_H
#define TEST_FRAMEWORK_H

#include "ast.h"
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    TEST_CASE,
    TEST_PROPERTY,
    TEST_INTEGRATION,
    TEST_FUZZ,
} TestKind;

typedef struct TestCase TestCase;
typedef struct TestCaseList TestCaseList;
typedef struct PropertyTest PropertyTest;
typedef struct PropertyTestList PropertyTestList;
typedef struct MockSpec MockSpec;
typedef struct MockSpecList MockSpecList;
typedef struct TestSpec TestSpec;
typedef struct TestSpecList TestSpecList;

struct MockSpec {
    char* function_name;
    ExprList* input_args;
    Expr* return_value;
    int call_sequence;
};

struct MockSpecList {
    MockSpec* mock;
    MockSpecList* next;
};

struct TestCase {
    char* description;
    ExprList* input_args;
    Expr* expected;
    MockSpecList* mocks;
    int line;
};

struct TestCaseList {
    TestCase* test_case;
    TestCaseList* next;
};

struct PropertyTest {
    char* description;
    ParamList* forall_vars;
    Expr* constraint;
    Expr* assertion;
    int num_cases;
};

struct PropertyTestList {
    PropertyTest* property;
    PropertyTestList* next;
};

struct TestSpec {
    TestKind kind;
    char* target_function;
    union {
        TestCaseList* test_cases;
        PropertyTestList* properties;
    } data;
    int line;
};

struct TestSpecList {
    TestSpec* spec;
    TestSpecList* next;
};

typedef struct TestResult {
    char* test_name;
    bool passed;
    char* expected_str;
    char* actual_str;
    char* error_message;
    int line;
    uint64_t duration_us;
} TestResult;

typedef struct TestResults {
    TestResult* results;
    int total;
    int passed;
    int failed;
    int skipped;
    uint64_t total_duration_us;
} TestResults;

TestSpec* test_spec_new(TestKind kind, const char* target, int line);
TestCase* test_case_new(const char* desc, ExprList* inputs, Expr* expected, int line);
MockSpec* mock_spec_new(const char* func_name, ExprList* args, Expr* ret_val);
PropertyTest* property_test_new(const char* desc, ParamList* vars, Expr* constraint, Expr* assertion);

TestCaseList* test_case_list_new(TestCase* tc, TestCaseList* next);
TestSpecList* test_spec_list_new(TestSpec* spec, TestSpecList* next);
MockSpecList* mock_spec_list_new(MockSpec* mock, MockSpecList* next);
PropertyTestList* property_test_list_new(PropertyTest* prop, PropertyTestList* next);

void free_test_spec(TestSpec* spec);
void free_test_results(TestResults* results);

#endif
