"""Positive/negative semantic tests, AST contract, HW2 reuse and real CLI tests."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw3.funny_frontend import Parser, BaseParser, parse, tokenize
from hw3.funny_types import check
from hw3.type_system import (BOOL, INT, TypeVar, array, concrete, display, encode,
                             function, resolve, unify)

ROOT = Path(__file__).resolve().parent


def program(body, params="", returns="r: int", uses=""):
    uses = f" uses ({uses})" if uses else ""
    return f"function f({params}) returns ({returns}){uses} {{ {body} }}"


def expressions(value):
    if isinstance(value, dict):
        if value.get("type") in {"Int", "Bool", "Name", "Binary", "Unary", "Call", "Index", "ArrayUpdate"}:
            yield value
        for child in value.values():
            yield from expressions(child)
    elif isinstance(value, list):
        for child in value:
            yield from expressions(child)


class SemanticCase(unittest.TestCase):
    def ok(self, source):
        result = check(source)
        self.assertEqual(result["errors"], [])
        for expression in expressions(result["ast"]):
            self.assertIn("inferred_type", expression)
            self.assertNotEqual(expression["inferred_type"], "error")
        json.dumps(result)
        return result

    def bad(self, source, *codes):
        result = check(source)
        actual = [e["code"] for e in result["errors"]]
        for code in codes:
            self.assertIn(code, actual, result["errors"])
        for error in result["errors"]:
            self.assertGreaterEqual(error["line"], 1)
            self.assertGreaterEqual(error["column"], 1)
            self.assertTrue(error["message"])
        json.dumps(result)
        return result


class FrontendTests(SemanticCase):
    def test_parser_reuses_hw2(self):
        self.assertTrue(issubclass(Parser, BaseParser))
        for name in ("expression", "block", "postfix", "primary", "unary"):
            self.assertIs(getattr(Parser, name), getattr(BaseParser, name))

    def test_untyped_hw2_program_parses_but_requires_signature_types(self):
        source = (ROOT.parent / "hw2" / "demo.funny").read_text(encoding="utf-8")
        tree, errors = parse(source)
        self.assertEqual(errors, [])
        self.assertEqual(tree["functions"][0]["params"], ["a", "n"])
        result = self.bad(source, "E_ANNOTATION_REQUIRED")
        self.assertEqual(sum(e["code"] == "E_ANNOTATION_REQUIRED" for e in result["errors"]), 3)

    def test_colon_comments_and_windows_positions(self):
        tokens = tokenize("// comment: text\r\nletx: int; let y;")
        self.assertEqual([(t.kind, t.line, t.column) for t in tokens[:3]],
                         [("IDENT", 2, 1), (":", 2, 5), ("IDENT", 2, 7)])
        self.assertEqual(tokens[4].kind, "LET")

    def test_unknown_type(self):
        self.bad(program("r = 1;", params="x: string"), "E_TYPE_UNKNOWN")

    def test_lexical_error_is_structured(self):
        result = self.bad("\n  @", "E_LEXICAL")
        self.assertIsNone(result["ast"])
        self.assertEqual((result["errors"][0]["line"], result["errors"][0]["column"]), (2, 3))

    def test_syntax_recovery_then_semantics(self):
        result = self.bad(program("r = ; absent = 0; r = 1;"), "E_SYNTAX", "E_UNKNOWN_NAME")
        self.assertEqual(len(result["ast"]["functions"][0]["body"]["statements"]), 2)

    def test_many_syntax_errors_terminate(self):
        result = self.bad(program("0; " * 300, returns=""), "E_SYNTAX")
        self.assertEqual(len(result["errors"]), 300)

    def test_invalid_call_statement_keeps_next_statement(self):
        source = "function f(a: int[]) returns (r: int) { length(a) + 1; r = 0; }"
        result = self.bad(source, "E_SYNTAX")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["ast"]["functions"][0]["body"]["statements"][0]["type"], "Assign")

    def test_empty_program(self):
        self.bad("", "E_SYNTAX")


class NameTests(SemanticCase):
    def test_unknown_rhs_and_target_both_reported(self):
        result = self.bad(program("unknown = missing; r = 0;"), "E_UNKNOWN_NAME")
        self.assertEqual(len(result["errors"]), 2)

    def test_use_before_declaration(self):
        self.bad(program("r = later; let later = 1; r = later;"), "E_UNKNOWN_NAME")

    def test_assignment_before_declaration(self):
        self.bad(program("later = 1; let later = 2; r = later;"), "E_UNKNOWN_NAME")

    def test_duplicate_parameter(self):
        self.bad(program("r = x;", params="x: int, x: int"), "E_DUPLICATE")

    def test_parameter_result_collision(self):
        self.bad(program("r = 1;", params="r: int"), "E_DUPLICATE")

    def test_duplicate_local_and_parameter(self):
        self.bad(program("let x = 2; r = x;", params="x: int"), "E_DUPLICATE")

    def test_duplicate_uses(self):
        self.bad(program("x = 1; r = x;", uses="x: int, x: int"), "E_DUPLICATE")

    def test_duplicate_function(self):
        self.bad(program("r = 1;") + program("r = 2;"), "E_DUPLICATE")

    def test_nested_shadowing_and_ids(self):
        result = self.ok(program("let x = 1; { let x = true; assert x; } r = x;"))
        symbols = [s for s in result["symbols"] if s["name"] == "x"]
        self.assertEqual([s["value_type"] for s in symbols], ["int", "bool"])
        self.assertNotEqual(symbols[0]["scope_id"], symbols[1]["scope_id"])
        self.assertNotEqual(symbols[0]["id"], symbols[1]["id"])

    def test_nested_local_does_not_escape(self):
        self.bad(program("{ let x = 1; } r = x;"), "E_UNKNOWN_NAME")

    def test_function_names_are_not_assignable(self):
        self.bad(program("f = 1; r = 0;"), "E_ASSIGN_FUNCTION")

    def test_symbol_ids_resolve_all_names(self):
        result = self.ok((ROOT / "examples/functions.funny").read_text())
        ids = {s["id"] for s in result["symbols"]}
        for expression in expressions(result["ast"]):
            if expression["type"] == "Name":
                self.assertIn(expression["symbol_id"], ids)


class TypeTests(SemanticCase):
    def test_integer_arithmetic(self):
        self.ok(program("r = -(x + 1) * 2 / 3 - 4;", params="x: int"))

    def test_boolean_logic_and_comparisons(self):
        self.ok(program("r = not b or x <= 0 and x != 2;", params="x: int, b: bool", returns="r: bool"))

    def test_boolean_equality(self):
        self.ok(program("r = true == false;", returns="r: bool"))

    def test_assignment_type_mismatch(self):
        self.bad(program("r = false;"), "E_TYPE_MISMATCH", "E_RESULT_UNASSIGNED")

    def test_local_explicit_annotation(self):
        self.ok(program("let x: int = 2; let b: bool = true; assert b; r = x;"))

    def test_bad_local_initializer(self):
        self.bad(program("let x: int = true; r = x;"), "E_TYPE_MISMATCH", "E_UNINITIALIZED")

    def test_all_operator_operand_errors_accumulate(self):
        result = self.bad(program("r = true + false;"), "E_TYPE_MISMATCH")
        self.assertEqual(sum(e["code"] == "E_TYPE_MISMATCH" for e in result["errors"]), 2)

    def test_unary_type_mismatch(self):
        self.bad(program("let b = not 1; r = -true;"), "E_TYPE_MISMATCH")

    def test_no_implicit_bool_int_coercion(self):
        self.bad(program("assert 1 == true; r = 0;"), "E_TYPE_MISMATCH")

    def test_arrays_and_length(self):
        self.ok(program("a[0] = 1; r = a[0] + length(a);", params="a: int[]"))

    def test_nested_arrays(self):
        self.ok(program("let row = a[0]; row[1] = 2; r = a[0][1];", params="a: int[][]"))

    def test_index_requires_int(self):
        self.bad(program("r = a[true];", params="a: int[]"), "E_TYPE_MISMATCH")

    def test_non_array_index_and_update(self):
        result = self.bad(program("x[0] = false; r = x[0];", params="x: int"), "E_NOT_ARRAY")
        self.assertEqual(sum(e["code"] == "E_NOT_ARRAY" for e in result["errors"]), 2)

    def test_array_element_type(self):
        self.bad(program("a[0] = false; r = 0;", params="a: int[]"), "E_TYPE_MISMATCH")

    def test_length_rejects_non_array(self):
        self.bad(program("r = length(1);"), "E_TYPE_MISMATCH")

    def test_length_is_instantiated_per_call(self):
        self.ok(program("r = length(a) + length(b);", params="a: int[], b: bool[]"))

    def test_length_arity_and_extra_arg_checked(self):
        self.bad(program("r = length(a, missing);", params="a: int[]"),
                 "E_ARGUMENT_COUNT", "E_UNKNOWN_NAME")

    def test_length_cannot_be_a_value(self):
        self.bad(program("let size = length; r = 0;"), "E_BUILTIN_VALUE", "E_CANNOT_INFER")

    def test_array_equality_explicitly_unsupported(self):
        self.bad(program("assert a == a; r = 0;", params="a: int[]"), "E_EQUALITY_TYPE")


class FunctionTests(SemanticCase):
    def test_forward_call(self):
        self.ok(program("r = g(1);") + "function g(x: int) returns (y: int) { y = x; }")

    def test_recursive_and_mutually_recursive(self):
        self.ok("function a(x: int) returns (r: bool) { "
                "if (x == 0) { r = true; } else { r = b(x - 1); } } "
                "function b(x: int) returns (r: bool) { r = a(x); }")

    def test_wrong_arity_and_argument_type(self):
        self.bad(program("r = g(true, 2);") + "function g(x: int) returns (y: int) { y = x; }",
                 "E_ARGUMENT_COUNT", "E_TYPE_MISMATCH")

    def test_calls_and_inferred_local(self):
        self.ok((ROOT / "examples/functions.funny").read_text())

    def test_function_value_unsupported(self):
        self.bad(program("let g = f; r = 1;"), "E_FUNCTION_VALUE", "E_CANNOT_INFER")

    def test_non_callable(self):
        self.bad(program("let x = 1; r = x();"), "E_NOT_CALLABLE")

    def test_unknown_function_still_checks_arguments(self):
        result = self.bad(program("r = missing(other);"), "E_UNKNOWN_NAME")
        self.assertEqual(sum(e["code"] == "E_UNKNOWN_NAME" for e in result["errors"]), 2)

    def test_chained_call_rejects_scalar(self):
        self.bad("function id(x: int) returns (r: int) { r = x; } " + program("r = id(1)(2);"),
                 "E_NOT_CALLABLE")

    def test_function_annotation_unsupported(self):
        self.bad(program("r = 0;", params="callback: func"), "E_TYPE_UNKNOWN")

    def test_unit_annotation_unsupported(self):
        self.bad(program("r = 0;", params="x: unit"), "E_TYPE_UNKNOWN")

    def test_tuple_annotation_unsupported(self):
        self.bad(program("r = 0;", params="x: (int, bool)"), "E_SYNTAX")

    def test_zero_and_multiple_results(self):
        result = self.ok("function empty() returns () {} "
                         "function pair() returns (a: int, b: bool) { a = 1; b = true; } "
                         "function main() returns (r: int) { "
                         "let empty_result = empty(); let pair_result = pair(); r = 0; }")
        types = {s["name"]: s["value_type"] for s in result["symbols"] if s["kind"] == "local"}
        self.assertEqual(types["empty_result"], "unit")
        self.assertEqual(types["pair_result"], {"kind": "tuple", "items": ["int", "bool"]})


class InferenceAndFlowTests(SemanticCase):
    def test_uses_and_let_inference(self):
        result = self.ok(program("x = 1; let y = x + 2; r = y;", uses="x"))
        self.assertEqual([s["value_type"] for s in result["symbols"] if s["name"] in ("x", "y")],
                         ["int", "int"])

    def test_first_valid_assignment_after_invalid_one(self):
        result = self.bad(program("let x; x = missing; x = true; assert x; r = 0;"), "E_UNKNOWN_NAME")
        self.assertEqual([s["value_type"] for s in result["symbols"] if s["name"] == "x"], ["bool"])
        self.assertEqual(len(result["errors"]), 1)

    def test_conflicting_assignment(self):
        result = self.bad(program("let x; x = 1; x = false; r = x;"), "E_TYPE_MISMATCH")
        self.assertEqual([s["value_type"] for s in result["symbols"] if s["name"] == "x"], ["int"])

    def test_cannot_infer_unused_local(self):
        self.bad(program("let x; r = 0;"), "E_CANNOT_INFER")

    def test_self_initialization(self):
        self.bad(program("let x = x; r = 0;"), "E_UNINITIALIZED", "E_CANNOT_INFER")

    def test_explicit_uninitialized_read(self):
        self.bad(program("let x: int; r = x;"), "E_UNINITIALIZED")

    def test_both_branches_initialize(self):
        self.ok(program("let x; if (b) { x = 1; } else { x = 2; } r = x;", params="b: bool"))

    def test_one_branch_does_not_initialize(self):
        self.bad(program("let x; if (b) { x = 1; } r = x;", params="b: bool"), "E_UNINITIALIZED")

    def test_branch_inference_conflict(self):
        self.bad(program("let x; if (b) { x = 1; } else { x = true; } r = 0;", params="b: bool"),
                 "E_TYPE_MISMATCH")

    def test_else_if_merges_all_paths(self):
        self.ok(program("if (x < 0) { r = -x; } else if (x == 0) { r = 1; } else { r = x; }",
                        params="x: int"))

    def test_loop_may_execute_zero_times(self):
        self.bad(program("let x; while (false) { x = 1; } r = x;"), "E_UNINITIALIZED")

    def test_loop_can_use_preinitialized_local(self):
        self.ok(program("let x = 0; while (x < 2) invariant x >= 0; { x = x + 1; } r = x;"))

    def test_missing_result_on_one_path(self):
        self.bad(program("if (b) { r = 1; }", params="b: bool"), "E_RESULT_UNASSIGNED")

    def test_ensures_sees_assigned_results_and_locals(self):
        self.ok("function f(x: int) returns (r: int) uses (tmp) "
                "requires x >= 0; ensures r == tmp; { tmp = x; r = tmp; }")

    def test_requires_cannot_read_unassigned_result(self):
        self.bad("function f() returns (r: int) requires r > 0; { r = 1; }", "E_UNINITIALIZED")

    def test_all_predicates_require_bool(self):
        result = self.bad("function f() returns (r: int) requires 1; ensures 1; { "
                          "if (1) {} while (1) invariant 1; {} assert 1; assume 1; r = 0; }",
                          "E_TYPE_MISMATCH")
        self.assertEqual(sum(e["code"] == "E_TYPE_MISMATCH" for e in result["errors"]), 7)

    def test_empty_contracts_keep_hw2_behavior(self):
        self.ok("function f() returns () requires; ensures; {}")

    def test_repeated_check_has_no_shared_state(self):
        source = program("let x = 1; r = x;")
        self.assertEqual(check(source), check(source))


class ArtifactTests(SemanticCase):
    def test_typed_hw2_demo(self):
        self.ok((ROOT / "examples/demo.funny").read_text())

    def test_negative_example_exact_codes_and_positions(self):
        actual = check((ROOT / "examples/errors.funny").read_text())["errors"]
        expected = json.loads((ROOT / "examples/errors.expected.json").read_text())
        self.assertEqual([{k: e[k] for k in ("code", "line", "column")} for e in actual], expected)

    def test_annotated_ast_snapshot(self):
        actual = self.ok((ROOT / "examples/basic.funny").read_text())
        expected = json.loads((ROOT / "examples/basic.expected.json").read_text())
        self.assertEqual(actual, expected)


class UnificationTests(unittest.TestCase):
    def test_simple_types_are_distinct(self):
        self.assertTrue(unify(INT, INT))
        self.assertFalse(unify(INT, BOOL))

    def test_structural_function_and_array_unification(self):
        t = TypeVar()
        self.assertTrue(unify(function([array(t)], t), function([array(INT)], INT)))
        self.assertEqual(resolve(t), INT)

    def test_occurs_check(self):
        t = TypeVar()
        self.assertFalse(unify(t, array(t)))
        self.assertIsNone(t.binding)

    def test_failed_constraint_rolls_back(self):
        t = TypeVar()
        self.assertFalse(unify(function([t], INT), function([BOOL], BOOL)))
        self.assertIsNone(t.binding)

    def test_unresolved_array_diagnostic(self):
        t = TypeVar()
        self.assertEqual(display(array(t)), "?[]")
        self.assertFalse(concrete(array(t)))
        self.assertEqual(encode(array(t)), {"kind": "array", "element": "error"})


class CommandLineTests(unittest.TestCase):
    def run_checker(self, *args, cwd=None, input=None):
        return subprocess.run([sys.executable, str(ROOT / "funny_types.py"), *map(str, args)],
                              cwd=cwd, input=input, capture_output=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=15)

    def test_json_stdout(self):
        result = self.run_checker(ROOT / "examples/demo.funny")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout)["errors"], [])

    def test_module_execution(self):
        result = subprocess.run(
            [sys.executable, "-m", "hw3.funny_types", "hw3/examples/demo.funny"],
            cwd=ROOT.parent, capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["errors"], [])

    def test_package_imports_reuse_same_hw2_parser(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from hw2.funny_parser import Parser; "
             "from hw3.funny_frontend import BaseParser; "
             "from hw3.funny_types import check; "
             "assert BaseParser is Parser; "
             "assert not check('function f() returns () {}')['errors']"],
            cwd=ROOT.parent, capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_output_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            result = self.run_checker(ROOT / "examples/demo.funny", "--out", output, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["schema_version"], "funny.typed-ast.v1")

    def test_semantic_error_exit_code_and_json(self):
        result = self.run_checker(ROOT / "examples/errors.funny")
        self.assertEqual(result.returncode, 1)
        self.assertIn("E_UNKNOWN_NAME", result.stderr)
        self.assertGreater(len(json.loads(result.stdout)["errors"]), 1)

    def test_lexical_error_still_emits_json(self):
        result = self.run_checker("-", input="@")
        self.assertEqual(result.returncode, 1)
        self.assertIsNone(json.loads(result.stdout)["ast"])

    def test_missing_file_exit_code(self):
        result = self.run_checker(ROOT / "not_found.funny")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Ошибка ввода/вывода", result.stderr)

    def test_stdin(self):
        result = self.run_checker("-", input=program("r = 1;"))
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
