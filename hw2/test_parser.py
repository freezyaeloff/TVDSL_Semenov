import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from funny_parser import ParseError, parse, tokenize

ROOT = Path(__file__).parent


class LexerTests(unittest.TestCase):
    def test_positions_and_skipped_tokens(self):
        tokens = tokenize("// comment\n  a[12] = 3;\nrequires true;")
        self.assertEqual(
            [(t.kind, t.text, t.line, t.column) for t in tokens],
            [("IDENT", "a", 2, 3), ("[", "[", 2, 4),
             ("INT", "12", 2, 5), ("]", "]", 2, 7),
             ("=", "=", 2, 9), ("INT", "3", 2, 11),
             (";", ";", 2, 12), ("REQUIRES", "requires", 3, 1),
             ("TRUE", "true", 3, 10), (";", ";", 3, 14),
             ("EOF", "", 3, 15)],
        )

    def test_maximal_munch(self):
        self.assertEqual([(t.kind, t.text) for t in tokenize("functionx == != 01")[:-1]],
                         [("IDENT", "functionx"), ("==", "=="),
                          ("!=", "!="), ("INT", "0"), ("INT", "1")])

    def test_bad_character_position(self):
        with self.assertRaisesRegex(ParseError, r"2:3:.*'@'"):
            tokenize("x\n  @")

    def test_non_ascii_comment_is_rejected_by_hw1(self):
        with self.assertRaisesRegex(ParseError, "1:4"):
            tokenize("// Привет")

    def test_windows_line_endings(self):
        self.assertEqual((tokenize("x\r\ny")[1].line, tokenize("x\r\ny")[1].column),
                         (2, 1))


class PositiveTests(unittest.TestCase):
    def test_ast_snapshot(self):
        source = "function f(x) returns (y) { y = x + 1; }"
        tree, errors = parse(source)
        expected = json.loads((ROOT / "expected_basic.json").read_text(encoding="utf-8"))
        self.assertEqual(errors, [])
        self.assertEqual(tree, expected)

    def test_empty_contracts(self):
        tree, errors = parse("function f() returns () requires; ensures; {}")
        self.assertEqual(errors, [])
        function = tree["functions"][0]
        self.assertEqual(function["requires"], [None])
        self.assertEqual(function["ensures"], [None])

    def test_contracts_and_uses(self):
        source = ("function sum(x,y) returns (z) uses (tmp) "
                  "requires x >= 0; ensures z >= x; { z = x + y; }")
        tree, errors = parse(source)
        self.assertEqual(errors, [])
        function = tree["functions"][0]
        self.assertEqual((function["params"], function["returns"], function["uses"]),
                         (["x", "y"], ["z"], ["tmp"]))
        self.assertEqual(function["requires"][0]["type"], "Binary")
        self.assertEqual(function["ensures"][0]["operator"], ">=")

    def test_array_update_desugars(self):
        tree, errors = parse("function f(a,i) returns (r) { a[i] = a[i] + 1; }")
        self.assertEqual(errors, [])
        statement = tree["functions"][0]["body"]["statements"][0]
        self.assertEqual(statement["type"], "Assign")
        self.assertEqual(statement["target"], "a")
        self.assertEqual(statement["value"]["type"], "ArrayUpdate")
        self.assertEqual(statement["value"]["array"]["name"], "a")
        self.assertEqual(statement["value"]["index"]["name"], "i")
        self.assertEqual(statement["value"]["value"]["left"]["type"], "Index")

    def test_precedence_and_left_associativity(self):
        tree, errors = parse("function f() returns (r) { r = 1 + 2 * 3 - 4 - 5; }")
        self.assertEqual(errors, [])
        expr = tree["functions"][0]["body"]["statements"][0]["value"]
        self.assertEqual(expr["operator"], "-")
        self.assertEqual(expr["left"]["operator"], "-")
        self.assertEqual(expr["left"]["left"]["operator"], "+")
        self.assertEqual(expr["left"]["left"]["right"]["operator"], "*")

    def test_boolean_and_unary(self):
        tree, errors = parse("function f(x) returns (r) { r = not false or -x < 0 and true; }")
        self.assertEqual(errors, [])
        expr = tree["functions"][0]["body"]["statements"][0]["value"]
        self.assertEqual(expr["operator"], "or")
        self.assertEqual(expr["left"]["type"], "Unary")
        self.assertEqual(expr["right"]["operator"], "and")

    def test_if_else_if(self):
        code = ("function f(x) returns (r) {"
                "if (x < 0) { r = -x; } else if (x == 0) { r = 1; } "
                "else { r = x; } }")
        tree, errors = parse(code)
        self.assertEqual(errors, [])
        condition = tree["functions"][0]["body"]["statements"][0]
        self.assertEqual(condition["type"], "If")
        self.assertEqual(condition["otherwise"]["type"], "If")
        self.assertEqual(condition["otherwise"]["otherwise"]["type"], "Block")

    def test_while_and_invariants(self):
        tree, errors = parse("function f() returns () { while (true) invariant 1 < 2; {} }")
        self.assertEqual(errors, [])
        loop = tree["functions"][0]["body"]["statements"][0]
        self.assertEqual(loop["type"], "While")
        self.assertEqual(len(loop["invariants"]), 1)

    def test_assert_assume_call_and_length(self):
        tree, errors = parse("function f(a) returns () { assert length(a) >= 0; assume ok(a); }")
        self.assertEqual(errors, [])
        first, second = tree["functions"][0]["body"]["statements"]
        self.assertEqual(first["type"], "Assert")
        self.assertEqual(first["expression"]["left"]["type"], "Call")
        self.assertEqual(second["type"], "Assume")

    def test_multiple_functions_and_comments(self):
        code = "// hi\nfunction f() returns () {} function g() returns () {}"
        tree, errors = parse(code)
        self.assertEqual(errors, [])
        self.assertEqual([x["name"] for x in tree["functions"]], ["f", "g"])

    def test_full_example(self):
        code = (ROOT / "demo.funny").read_text(encoding="utf-8")
        tree, errors = parse(code)
        self.assertEqual(errors, [])
        self.assertEqual(len(tree["functions"]), 1)
        self.assertEqual(len(tree["functions"][0]["body"]["statements"]), 5)


class NegativeTests(unittest.TestCase):
    def assert_error(self, code, text):
        _, errors = parse(code)
        self.assertTrue(errors, f"Должна быть ошибка в {code!r}")
        self.assertIn(text, " ".join(errors))

    def test_empty_input(self):
        self.assert_error("", "1:1: пустая программа")

    def test_unclosed_parenthesis(self):
        self.assert_error("function f(x returns (r) {}", "ожидалось )")

    def test_unclosed_bracket(self):
        self.assert_error("function f(a) returns () { a[0 = 1; }", "ожидалось ]")

    def test_unclosed_block(self):
        self.assert_error("function f() returns () { x = 1;", "ожидалось }")

    def test_wrong_assignment_operator(self):
        self.assert_error("function f() returns () { x == 1; }", "ожидалось =")

    def test_extra_tokens(self):
        self.assert_error("garbage function f() returns () {} garbage", "ожидалось объявление function")

    def test_missing_expression_with_recovery(self):
        tree, errors = parse("function f() returns () { x = ; y = 2; }")
        self.assertEqual(len(errors), 1)
        self.assertIn("1:31: ожидалось выражение", errors[0])
        body = tree["functions"][0]["body"]["statements"]
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["target"], "y")

    def test_two_errors_and_next_function(self):
        code = ("function a() returns () { x = ; y = ; z = 3; } "
                "function b() returns () { t = 2; }")
        tree, errors = parse(code)
        self.assertEqual(len(errors), 2)
        self.assertEqual([f["name"] for f in tree["functions"]], ["a", "b"])
        self.assertEqual(tree["functions"][0]["body"]["statements"][0]["target"], "z")

    def test_missing_function_brace_recovers_to_next_function(self):
        code = ("function a() returns () { x = 1; "
                "function b() returns () { y = 2; }")
        tree, errors = parse(code)
        self.assertEqual(len(errors), 1)
        self.assertEqual([f["name"] for f in tree["functions"]], ["b"])

    def test_invalid_character(self):
        with self.assertRaisesRegex(ParseError, "1:31: неизвестный символ"):
            parse("function f() returns () { x = @; }")

    def test_many_broken_statements_do_not_loop(self):
        code = "function f() returns () { " + "@" * 3
        with self.assertRaises(ParseError):
            parse(code)
        code = "function f() returns () { " + "0; " * 300 + "}"
        tree, errors = parse(code)
        self.assertEqual(len(errors), 300)
        self.assertEqual(len(tree["functions"]), 1)


class CommandLineTests(unittest.TestCase):
    def run_parser(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(ROOT.resolve() / "funny_parser.py"), *map(str, args)],
            cwd=cwd, capture_output=True, encoding="utf-8", timeout=10,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_json_stdout(self):
        result = self.run_parser(ROOT.resolve() / "demo.funny")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout)["functions"][0]["name"], "process")

    def test_output_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ast.json"
            result = self.run_parser(ROOT.resolve() / "demo.funny", "--out", output,
                                     cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["type"], "Program")

    def test_errors_exit_code_and_partial_ast(self):
        result = self.run_parser(ROOT.resolve() / "errors.funny")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.count("Ошибка:"), 2)
        tree = json.loads(result.stdout)
        statements = tree["functions"][0]["body"]["statements"]
        self.assertTrue(statements)


def run_tests():
    class ReportResult(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.rows = []

        def addSuccess(self, test):
            super().addSuccess(test)
            self.rows.append((test.id().split(".", 1)[-1], "PASS"))

        def addFailure(self, test, error):
            super().addFailure(test, error)
            self.rows.append((test.id().split(".", 1)[-1], "FAIL"))

        def addError(self, test, error):
            super().addError(test, error)
            self.rows.append((test.id().split(".", 1)[-1], "ERROR"))

    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2, resultclass=ReportResult).run(suite)
    lines = ["# HW2. Результаты тестов", "",
             "Команда: `python test_parser.py` или `python funny_parser.py --tests`.", "",
             "Ожидаемые AST, токены и ошибки проверяются утверждениями в `test_parser.py`.", "",
             "| Тест | Результат |", "| --- | --- |"]
    lines.extend(f"| `{name}` | {status} |" for name, status in result.rows)
    lines.extend(["", f"Всего: {result.testsRun}. "
                  + ("ALL PASS." if result.wasSuccessful() else "Есть ошибки."), ""])
    (ROOT / "tests.md").write_text("\n".join(lines), encoding="utf-8")
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_tests() else 1)
