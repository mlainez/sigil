#ifndef DESUGAR_H
#define DESUGAR_H

#include "ast.h"

// Desugar Agent-layer constructs (while, loop, break, continue) to Core-layer constructs
// (set, call, label, goto, ifnot, ret)
//
// This pass transforms:
//   - while loops -> label + ifnot + goto
//   - loop (infinite) -> label + goto
//   - break -> goto to end label
//   - continue -> goto to start label
//
// After desugaring, only Core constructs remain in the AST.

// Desugar an entire module (all functions)
Module* desugar_module(Module* module);

// Desugar a single function body
Expr* desugar_expr(Expr* expr);

// Desugar a statement sequence (used for function bodies)
ExprList* desugar_statement_list(ExprList* stmts);

#endif // DESUGAR_H
