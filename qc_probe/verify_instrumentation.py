"""
Mechanical, automated check that hmm_hybrid_instrumented.py's Reset() and
rebalance() methods contain the author's exact original algorithmic
branches, with ONLY the marked logging statements added.

Method:
  1. Parse reference_original_hmm_hybrid.py and hmm_hybrid_instrumented.py
     with Python's `ast` module (syntax tree, not execution -- neither file
     can actually be imported/run outside a QuantConnect runtime, since
     QCAlgorithm/Resolution/etc. are only real at runtime there; see
     README.md for what "runnable" would actually require).
  2. Locate the `Reset` and `rebalance` FunctionDef nodes inside the
     HMMHybrid / HMMHybridInstrumented class in each file.
  3. From the INSTRUMENTED method body, mechanically strip statements that
     match the logging-instrumentation pattern:
       - `self.Log(...)` expression statements,
       - the `switch_before = self.switch` capture assignment.
     No other statement is touched or reordered.
  4. Compare the remaining statement list against the ORIGINAL method body
     using `ast.dump(node, annotate_fields=False)` (which already ignores
     line/column/formatting -- only actual code structure matters) for
     structural equality, statement by statement.

This does NOT prove the instrumented file will run correctly in QuantConnect
(that needs a real LEAN/QC runtime -- see README.md). It proves exactly one
thing, mechanically: after removing the marked logging additions, the
Reset()/rebalance() algorithmic branches are structurally identical to the
supplied author source.

Usage:
  python qc_probe/verify_instrumentation.py
"""

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
ORIGINAL_PATH = HERE / "reference_original_hmm_hybrid.py"
INSTRUMENTED_PATH = HERE / "hmm_hybrid_instrumented.py"

METHODS_TO_CHECK = ["Reset", "rebalance"]


def _find_class_method(tree, method_name):
    """Find the first method with this name inside any ClassDef in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    return None


def _is_self_log_call(stmt):
    """True if `stmt` is an expression statement calling self.Log(...)."""
    if not isinstance(stmt, ast.Expr):
        return False
    call = stmt.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    return (isinstance(func, ast.Attribute) and func.attr == "Log"
            and isinstance(func.value, ast.Name) and func.value.id == "self")


def _is_switch_before_capture(stmt):
    """True if `stmt` is exactly `switch_before = self.switch`."""
    if not isinstance(stmt, ast.Assign):
        return False
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return False
    if stmt.targets[0].id != "switch_before":
        return False
    val = stmt.value
    return (isinstance(val, ast.Attribute) and val.attr == "switch"
            and isinstance(val.value, ast.Name) and val.value.id == "self")


_BLOCK_FIELDS = ("body", "orelse", "finalbody")


def _strip_statement_list(stmts):
    """Remove matching statements from this list, then recurse into every
    nested block (If/For/While/Try/With ... bodies) so nothing is missed
    regardless of nesting depth."""
    kept = []
    for s in stmts:
        if _is_self_log_call(s) or _is_switch_before_capture(s):
            continue
        for field in _BLOCK_FIELDS:
            if hasattr(s, field):
                setattr(s, field, _strip_statement_list(getattr(s, field)))
        if isinstance(s, ast.Try):
            for handler in s.handlers:
                handler.body = _strip_statement_list(handler.body)
        kept.append(s)
    return kept


def strip_instrumentation(body):
    """Remove ONLY self.Log(...) calls and the switch_before capture line,
    at ANY nesting depth (top-level and inside if/else/for/while/try/with)."""
    return _strip_statement_list(list(body))


def normalize(stmt):
    return ast.dump(stmt, annotate_fields=False)


def compare_method(method_name, original_tree, instrumented_tree):
    orig_fn = _find_class_method(original_tree, method_name)
    inst_fn = _find_class_method(instrumented_tree, method_name)

    if orig_fn is None:
        return False, f"'{method_name}' not found in {ORIGINAL_PATH.name}"
    if inst_fn is None:
        return False, f"'{method_name}' not found in {INSTRUMENTED_PATH.name}"

    orig_stmts = [normalize(s) for s in orig_fn.body]
    inst_stmts_stripped = [normalize(s) for s in strip_instrumentation(inst_fn.body)]

    if orig_stmts == inst_stmts_stripped:
        return True, (f"MATCH: {len(orig_stmts)} statements, identical after "
                      f"stripping {len(inst_fn.body) - len(strip_instrumentation(inst_fn.body))} "
                      f"logging statement(s)")

    # Produce a precise diff for the first divergence, if any.
    for i, (o, s) in enumerate(zip(orig_stmts, inst_stmts_stripped)):
        if o != s:
            return False, (f"MISMATCH at statement index {i}:\n"
                           f"  original    : {o}\n"
                           f"  instrumented: {s}")
    return False, (f"MISMATCH: different statement counts "
                   f"(original={len(orig_stmts)}, instrumented(stripped)={len(inst_stmts_stripped)})")


def main():
    original_src = ORIGINAL_PATH.read_text()
    instrumented_src = INSTRUMENTED_PATH.read_text()

    # Syntax-level parse check for both files (does NOT prove importability
    # under a real QC runtime -- QCAlgorithm/Resolution/etc. are not
    # resolvable outside that runtime; see README.md).
    try:
        original_tree = ast.parse(original_src, filename=str(ORIGINAL_PATH))
        print(f"[syntax] {ORIGINAL_PATH.name}: parses as valid Python 3 -- OK")
    except SyntaxError as e:
        print(f"[syntax] {ORIGINAL_PATH.name}: SYNTAX ERROR: {e}")
        return 1

    try:
        instrumented_tree = ast.parse(instrumented_src, filename=str(INSTRUMENTED_PATH))
        print(f"[syntax] {INSTRUMENTED_PATH.name}: parses as valid Python 3 -- OK")
    except SyntaxError as e:
        print(f"[syntax] {INSTRUMENTED_PATH.name}: SYNTAX ERROR: {e}")
        return 1

    print()
    all_ok = True
    for method_name in METHODS_TO_CHECK:
        ok, detail = compare_method(method_name, original_tree, instrumented_tree)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {method_name}(): {detail}")
        all_ok = all_ok and ok

    print()
    if all_ok:
        print("RESULT: instrumented Reset()/rebalance() are structurally "
             "equivalent to the supplied author source, after removing ONLY "
             "the marked logging additions.")
    else:
        print("RESULT: at least one method diverges beyond the marked "
             "logging additions -- see MISMATCH detail above.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
