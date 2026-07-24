"""
Mechanical, automated check that Main.py is the reference author source with
NOTHING added or changed except the module docstring and a single
`from AlgorithmImports import *` import line.

Unlike verify_instrumentation.py (which checks two specific methods after
stripping marked logging), this compares the ENTIRE module body: every
class, every method, every statement in Main.py must be
`ast.dump()`-identical to reference_original_hmm_hybrid.py once exactly two
things are removed from Main.py's parsed body -- the leading module
docstring (an Expr(Constant(str)) node) and the
`from AlgorithmImports import *` ImportFrom node. No logging was added, no
class was renamed, no line was reordered.

Usage:
  python qc_probe/verify_main.py
"""

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
REFERENCE_PATH = HERE / "reference_original_hmm_hybrid.py"
MAIN_PATH = HERE / "Main.py"

# reference_original_hmm_hybrid.py carries a header comment block (not part
# of the AST -- comments aren't nodes) so no line-skipping is needed on that
# side; parse it whole.


def _is_algorithm_imports_line(node):
    return isinstance(node, ast.ImportFrom) and node.module == "AlgorithmImports"


def _is_module_docstring(node):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def main():
    reference_src = REFERENCE_PATH.read_text()
    main_src = MAIN_PATH.read_text()

    try:
        reference_tree = ast.parse(reference_src, filename=str(REFERENCE_PATH))
        print(f"[syntax] {REFERENCE_PATH.name}: parses as valid Python 3 -- OK")
    except SyntaxError as e:
        print(f"[syntax] {REFERENCE_PATH.name}: SYNTAX ERROR: {e}")
        return 1

    try:
        main_tree = ast.parse(main_src, filename=str(MAIN_PATH))
        print(f"[syntax] {MAIN_PATH.name}: parses as valid Python 3 -- OK")
    except SyntaxError as e:
        print(f"[syntax] {MAIN_PATH.name}: SYNTAX ERROR: {e}")
        return 1

    main_body_filtered = [n for n in main_tree.body
                          if not _is_algorithm_imports_line(n) and not _is_module_docstring(n)]
    removed_count = len(main_tree.body) - len(main_body_filtered)

    reference_dump = ast.dump(reference_tree, annotate_fields=False)
    main_dump = ast.dump(ast.Module(body=main_body_filtered, type_ignores=[]), annotate_fields=False)

    print()
    if reference_dump == main_dump:
        print(f"[PASS] Main.py MATCHES reference_original_hmm_hybrid.py exactly, "
             f"after removing {removed_count} non-algorithmic node(s) "
             f"(module docstring + AlgorithmImports import).")
        print("RESULT: Main.py is the literal author algorithm, unmodified.")
        return 0

    print("[FAIL] Main.py diverges from the reference beyond the docstring/import.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
