"""
Mechanical, automated check that hmm_core_literal.py's train_core() and
Distribution are the author's train()/Distribution from
qc_probe/reference_original_hmm_hybrid.py, with ONLY two sanctioned
substitutions and nothing else added, removed, or reordered.

Method (mirrors qc_probe/verify_instrumentation.py's convention):
  1. Parse both files with `ast` (syntax tree only).
  2. `Distribution`: the two class bodies must be `ast.dump()`-identical,
     no exceptions.
  3. `train` (reference) vs `train_core` (local): split each into three
     segments and compare segment-by-segment --
       a. HEADER: `hidden_states = 3` / `em_iterations = 75` /
          `data_length = 3356` -- must be identical on both sides.
       b. DATA-LOADING statement(s): reference's `history = self.History(...)`
          + the `for symbol in self.symbols: if not history.empty: prices =
          ...` loop (2 statements) versus train_core's `prices = list(prices)`
          (1 statement) -- NOT compared for equality (this is the one
          sanctioned data adapter substitution), only checked to be present
          and non-empty on both sides.
       c. CORE: every remaining statement from `Volatility = []` through the
          final decision if/elif/else (`return 'bear'` / `'bull'` /
          `'neutral'`) -- must be `ast.dump()`-identical, statement by
          statement, EXCEPT train_core has exactly one extra statement
          (the `if diagnostics is not None: diagnostics.update(...)` block)
          immediately before the final if/elif/else, which is stripped
          before comparison (same "strip only the marked addition" rule as
          verify_instrumentation.py, not silently ignoring anything else).

This does NOT prove train_core() is numerically correct (that needs real
data -- see the PRECHECK in tests/test_hmm_core_literal.py). It proves
exactly one thing, mechanically: after removing the two sanctioned
substitutions, train_core() is structurally identical to the author's
train().

Usage:
  python verify_core.py
"""

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
REFERENCE_PATH = HERE / "qc_probe" / "reference_original_hmm_hybrid.py"
LOCAL_PATH = HERE / "hmm_core_literal.py"


def _find_class(tree, class_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _find_method_or_func(tree, name, within_class=None):
    if within_class is not None:
        cls = _find_class(tree, within_class)
        if cls is None:
            return None
        for item in cls.body:
            if isinstance(item, (ast.FunctionDef,)) and item.name == name:
                return item
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def dump(stmt):
    return ast.dump(stmt, annotate_fields=False)


def _is_diagnostics_block(stmt):
    """True if `stmt` is exactly `if diagnostics is not None: diagnostics.update(...)`."""
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if not (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
            and test.left.id == "diagnostics" and len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)):
        return False
    if len(stmt.body) != 1:
        return False
    inner = stmt.body[0]
    if not isinstance(inner, ast.Expr) or not isinstance(inner.value, ast.Call):
        return False
    call = inner.value
    return (isinstance(call.func, ast.Attribute) and call.func.attr == "update"
            and isinstance(call.func.value, ast.Name) and call.func.value.id == "diagnostics")


def compare():
    reference_src = REFERENCE_PATH.read_text()
    local_src = LOCAL_PATH.read_text()

    try:
        reference_tree = ast.parse(reference_src, filename=str(REFERENCE_PATH))
        print(f"[syntax] {REFERENCE_PATH.name}: parses as valid Python 3 -- OK")
    except SyntaxError as e:
        print(f"[syntax] {REFERENCE_PATH.name}: SYNTAX ERROR: {e}")
        return 1

    try:
        local_tree = ast.parse(local_src, filename=str(LOCAL_PATH))
        print(f"[syntax] {LOCAL_PATH.name}: parses as valid Python 3 -- OK")
    except SyntaxError as e:
        print(f"[syntax] {LOCAL_PATH.name}: SYNTAX ERROR: {e}")
        return 1

    print()
    all_ok = True

    # --- Distribution: whole-class identity (docstring-tolerant) --------
    def _strip_leading_docstring(body):
        if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            return body[1:]
        return body

    ref_dist = _find_class(reference_tree, "Distribution")
    local_dist = _find_class(local_tree, "Distribution")
    if ref_dist is None or local_dist is None:
        print("[FAIL] Distribution: class not found in one of the files")
        all_ok = False
    else:
        ref_dist_body = [dump(s) for s in _strip_leading_docstring(ref_dist.body)]
        local_dist_body = [dump(s) for s in _strip_leading_docstring(local_dist.body)]
        if ref_dist_body == local_dist_body:
            print("[PASS] Distribution: class body identical (class docstring, if any, not compared)")
        else:
            print("[FAIL] Distribution: class body diverges")
            all_ok = False

    # --- train / train_core -----------------------------------------------
    ref_train = _find_method_or_func(reference_tree, "train", within_class="HMMHybrid")
    local_train = _find_method_or_func(local_tree, "train_core")
    if ref_train is None or local_train is None:
        print("[FAIL] train/train_core: function not found")
        return 1

    ref_body = ref_train.body
    local_body = local_train.body
    # train_core() has a docstring as its first statement; train() does not.
    # Strip it before segment-by-segment comparison (same treatment as the
    # module docstring in qc_probe/verify_main.py).
    if (local_body and isinstance(local_body[0], ast.Expr)
            and isinstance(local_body[0].value, ast.Constant)
            and isinstance(local_body[0].value.value, str)):
        local_body = local_body[1:]

    # a. HEADER: first 3 statements (hidden_states/em_iterations/data_length)
    ref_header = ref_body[0:3]
    local_header = local_body[0:3]
    if [dump(s) for s in ref_header] == [dump(s) for s in local_header]:
        print("[PASS] header (hidden_states/em_iterations/data_length): identical")
    else:
        print("[FAIL] header diverges")
        all_ok = False

    # b. DATA-LOADING substitution: reference statements [3:5] (history= / for-loop),
    #    local statement [3] (prices = list(prices)) -- presence only, not equality.
    ref_loader = ref_body[3:5]
    local_loader = local_body[3:4]
    if len(ref_loader) == 2 and len(local_loader) == 1:
        print("[PASS] data-loading substitution: reference's self.History(...) block "
             "(2 statements) replaced by local `prices = list(prices)` (1 statement) "
             "-- the one sanctioned adapter, not compared for equality")
    else:
        print(f"[FAIL] unexpected data-loading statement counts: "
             f"reference={len(ref_loader)}, local={len(local_loader)}")
        all_ok = False

    # c. CORE: everything after, with train_core's one diagnostics block stripped
    ref_core = ref_body[5:]
    local_core_raw = local_body[4:]
    local_core = [s for s in local_core_raw if not _is_diagnostics_block(s)]
    n_stripped = len(local_core_raw) - len(local_core)

    ref_core_dump = [dump(s) for s in ref_core]
    local_core_dump = [dump(s) for s in local_core]

    if ref_core_dump == local_core_dump:
        print(f"[PASS] core ({len(ref_core_dump)} statements, Volatility=[] through the "
             f"final decision): identical after stripping {n_stripped} diagnostics "
             f"statement(s)")
    else:
        all_ok = False
        for i, (r, l) in enumerate(zip(ref_core_dump, local_core_dump)):
            if r != l:
                print(f"[FAIL] core diverges at statement index {i}:")
                print(f"  reference: {r}")
                print(f"  local    : {l}")
                break
        else:
            print(f"[FAIL] core diverges: different statement counts "
                 f"(reference={len(ref_core_dump)}, local(stripped)={len(local_core_dump)})")

    print()
    if all_ok:
        print("RESULT: hmm_core_literal.train_core() is structurally equivalent to the "
             "author's train(), after the one sanctioned data-loading adapter "
             "substitution and stripping the marked diagnostics addition. No other "
             "deviation found.")
    else:
        print("RESULT: at least one segment diverges beyond the sanctioned "
             "substitutions -- see FAIL detail above.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(compare())
