#include "ast_export.h"
#include "test_framework.h"
#include <string.h>

// Simple type to string converter
static const char* type_to_string(Type* type) {
    if (!type) return "unit";
    switch (type->kind) {
        case TYPE_INT: return "int";
        case TYPE_FLOAT: return "float";
        case TYPE_STRING: return "string";
        case TYPE_BOOL: return "bool";
        case TYPE_UNIT: return "unit";
        case TYPE_BYTES: return "bytes";
        case TYPE_ARRAY: return "array";
        case TYPE_MAP: return "map";
        case TYPE_JSON: return "json";
        case TYPE_OPTION: return "option";
        case TYPE_RESULT: return "result";
        case TYPE_CHANNEL: return "channel";
        default: return "unknown";
    }
}

// Export type to S-expression
void ast_export_type(FILE* out, Type* type) {
    if (!type) {
        fprintf(out, "unit");
        return;
    }
    fprintf(out, "%s", type_to_string(type));
}

// Export expression to S-expression
void ast_export_expr(FILE* out, Expr* expr) {
    if (!expr) {
        fprintf(out, "(unit)");
        return;
    }
    
    switch (expr->kind) {
        case EXPR_LIT_INT:
            fprintf(out, "(lit_int ");
            ast_export_type(out, expr->type);
            fprintf(out, " %lld)", (long long)expr->data.int_val);
            break;
            
        case EXPR_LIT_FLOAT:
            fprintf(out, "(lit_float ");
            ast_export_type(out, expr->type);
            fprintf(out, " %f)", expr->data.float_val);
            break;
            
        case EXPR_LIT_STRING:
            fprintf(out, "(lit_string \"%s\")", expr->data.string_val);
            break;
            
        case EXPR_LIT_BOOL:
            fprintf(out, "(lit_bool %s)", expr->data.bool_val ? "true" : "false");
            break;
            
        case EXPR_LIT_UNIT:
            fprintf(out, "(unit)");
            break;
            
        case EXPR_VAR:
            fprintf(out, "(var %s)", expr->data.var.name);
            break;
            
        case EXPR_APPLY:
            fprintf(out, "(call ");
            ast_export_expr(out, expr->data.apply.func);
            ExprList* arg = expr->data.apply.args;
            while (arg) {
                fprintf(out, " ");
                ast_export_expr(out, arg->expr);
                arg = arg->next;
            }
            fprintf(out, ")");
            break;
            
        case EXPR_IF:
            fprintf(out, "(if ");
            ast_export_expr(out, expr->data.if_expr.cond);
            fprintf(out, " ");
            ast_export_expr(out, expr->data.if_expr.then_expr);
            fprintf(out, " ");
            ast_export_expr(out, expr->data.if_expr.else_expr);
            fprintf(out, ")");
            break;
            
        case EXPR_SEQ:
            fprintf(out, "(seq");
            ExprList* seq = expr->data.tuple.elements;
            while (seq) {
                fprintf(out, "\n  ");
                ast_export_expr(out, seq->expr);
                seq = seq->next;
            }
            fprintf(out, ")");
            break;
            
        default:
            fprintf(out, "(unknown)");
            break;
    }
}

// Export function definition to S-expression
void ast_export_definition(FILE* out, Definition* def) {
    if (!def) return;
    
    switch (def->kind) {
        case DEF_FUNCTION: {
            fprintf(out, "(fn %s ", def->name);
            
            // Export parameters
            fprintf(out, "(");
            ParamList* param = def->data.func.params;
            while (param) {
                fprintf(out, "(%s ", param->param->name);
                ast_export_type(out, param->param->type);
                fprintf(out, ")");
                if (param->next) fprintf(out, " ");
                param = param->next;
            }
            fprintf(out, ") -> ");
            
            // Export return type
            ast_export_type(out, def->data.func.return_type);
            
            // Export body
            fprintf(out, "\n  ");
            ast_export_expr(out, def->data.func.body);
            fprintf(out, ")\n");
            break;
        }
        
        case DEF_TEST_SPEC: {
            TestSpec* spec = (TestSpec*)def->data.test.test_spec;
            if (!spec) break;
            
            fprintf(out, "(test-spec %s\n", spec->target_function);
            
            TestCaseList* tc = spec->data.test_cases;
            while (tc) {
                fprintf(out, "    (case \"%s\"\n", tc->test_case->description);
                
                // Export mocks if any
                if (tc->test_case->mocks) {
                    MockSpecList* mock = tc->test_case->mocks;
                    while (mock) {
                        fprintf(out, "      (mock (%s", mock->mock->function_name);
                        ExprList* arg = mock->mock->input_args;
                        while (arg) {
                            fprintf(out, " ");
                            ast_export_expr(out, arg->expr);
                            arg = arg->next;
                        }
                        fprintf(out, ") ");
                        ast_export_expr(out, mock->mock->return_value);
                        fprintf(out, ")\n");
                        mock = mock->next;
                    }
                }
                
                // Export input
                fprintf(out, "      (input");
                ExprList* input = tc->test_case->input_args;
                while (input) {
                    fprintf(out, " ");
                    ast_export_expr(out, input->expr);
                    input = input->next;
                }
                fprintf(out, ")\n");
                
                // Export expected result
                fprintf(out, "      (expect ");
                ast_export_expr(out, tc->test_case->expected);
                fprintf(out, "))\n");
                
                tc = tc->next;
            }
            
            fprintf(out, "  )\n");
            break;
        }
        
        case DEF_PROPERTY_SPEC: {
            TestSpec* spec = (TestSpec*)def->data.property.property_spec;
            if (!spec) break;
            
            fprintf(out, "(property-spec %s\n", spec->target_function);
            
            PropertyTestList* prop = spec->data.properties;
            while (prop) {
                fprintf(out, "    (property \"%s\"\n", prop->property->description);
                fprintf(out, "      (forall (");
                
                ParamList* var = prop->property->forall_vars;
                while (var) {
                    fprintf(out, "(%s ", var->param->name);
                    ast_export_type(out, var->param->type);
                    fprintf(out, ")");
                    if (var->next) fprintf(out, " ");
                    var = var->next;
                }
                fprintf(out, ")\n");
                
                if (prop->property->constraint) {
                    fprintf(out, "        (constraint ");
                    ast_export_expr(out, prop->property->constraint);
                    fprintf(out, ")\n");
                }
                
                fprintf(out, "        ");
                ast_export_expr(out, prop->property->assertion);
                fprintf(out, "))\n");
                
                prop = prop->next;
            }
            
            fprintf(out, "  )\n");
            break;
        }
        
        case DEF_META_NOTE: {
            fprintf(out, "(meta-note \"%s\")\n", def->data.meta_note.note_text);
            break;
        }
        
        default:
            break;
    }
}

// Export entire module to S-expression
void ast_export_module(FILE* out, Module* module) {
    if (!module) return;
    
    fprintf(out, "(mod %s\n", module->name);
    
    DefList* def = module->definitions;
    while (def) {
        fprintf(out, "  ");
        ast_export_definition(out, def->def);
        def = def->next;
    }
    
    fprintf(out, ")\n");
}
