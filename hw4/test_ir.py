import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw3.funny_types import check
from hw4.flow import analyze, live_out
from hw4.funny_ir import format_text, stage
from hw4.interpreter import run
from hw4.ir import generate
from hw4.optimize import optimize

ROOT = Path(__file__).resolve().parent
HW3 = ROOT.parent / "hw3" / "examples"


def compile_source(source):
    tree = check(source)
    if tree["errors"]:
        raise AssertionError(tree["errors"])
    return generate(tree)


def example(name):
    return compile_source((ROOT / "examples" / f"{name}.funny").read_text(encoding="utf-8"))


def single(body, params="x: int", returns="r: int"):
    return compile_source(f"function f({params}) returns ({returns}) {{ {body} }}")


def ops(program, name="f"):
    return [ins["op"] for code in program["functions"][name]["blocks"].values() for ins in code]


class IRTests(unittest.TestCase):
    def same_results(self, program, name, cases):
        for flags in itertools.product((False, True), repeat=3):
            with self.subTest(flags=flags):
                result = optimize(program, *flags)
                for args, expected in cases:
                    self.assertEqual(run(program, name, args), expected)
                    self.assertEqual(run(result, name, args), expected)

    def test_hw3_ast_file(self):
        tree = json.loads((HW3 / "basic.expected.json").read_text(encoding="utf-8"))
        ir = generate(tree)
        self.same_results(ir, "f", [([4], 5), ([-1], 0)])
        self.assertEqual(ir["functions"]["f"]["types"], {"v2": "int", "v3": "int", "t0": "int"})

    def test_rejects_incorrect_ast(self):
        for tree in (check("@"), check("function f() returns (r: int) {r = false;}"),
                     {"schema_version": "old"}):
            with self.assertRaises(ValueError):
                generate(tree)

    def test_arithmetic_example(self):
        ir = example("basic")
        self.same_results(ir, "calc", [([0], 0), ([4], 20), ([-7], -35)])
        self.assertEqual(analyze(ir["functions"]["calc"])["metrics"],
                         {"blocks": 1, "instructions": 9, "temporaries": 4, "colors": 1})
        self.assertEqual(analyze(optimize(ir)["functions"]["calc"])["metrics"],
                         {"blocks": 1, "instructions": 5, "temporaries": 2, "colors": 1})

    def test_constant_branch(self):
        ir = example("branch")
        self.same_results(ir, "choose", [([-3], -6), ([4], 8)])
        before = analyze(ir["functions"]["choose"])
        after = analyze(optimize(ir)["functions"]["choose"])
        self.assertEqual(before["metrics"]["blocks"], 4)
        self.assertEqual(after["metrics"]["blocks"], 3)
        self.assertEqual(after["cfg"], {"B0": ["B1"], "B1": ["B2"], "B2": []})
        without_constants = optimize(ir, constants=False)["functions"]["choose"]
        self.assertEqual(analyze(without_constants)["cfg"], before["cfg"])

    def test_constant_false_loop(self):
        ir = single("r = x; while (false) { r = 10 / 0; }")
        self.same_results(ir, "f", [([4], 4)])
        self.assertNotIn("/", ops(optimize(ir)))

    def test_loop_and_call(self):
        self.same_results(example("loop"), "sum", [([-2], 0), ([0], 0), ([2], 1), ([5], 19)])

    def test_hw3_branches_and_forward_calls(self):
        ir = compile_source((HW3 / "functions.funny").read_text(encoding="utf-8"))
        self.same_results(ir, "main", [([-5], 6), ([0], 1), ([7], 8)])
        self.same_results(ir, "inspect", [([[]], ()), ([[True, False]], ())])

    def test_hw3_arrays_and_contracts(self):
        ir = compile_source((HW3 / "demo.funny").read_text(encoding="utf-8"))
        array = [-3, 2, 7]
        self.same_results(ir, "process", [([array, 3], 9), ([[], 0], 0)])
        self.assertEqual(array, [-3, 2, 7])

    def test_array_update_value(self):
        ir = single("let old = a; a[i] = 9; r = a[i] - old[i];", "a: int[], i: int")
        self.same_results(ir, "f", [([[3, 7], 0], 6), ([[3, 7], 1], 2)])

    def test_named_results_and_shadowing(self):
        ir = single("r = x; {let x = 9; s = x;} r = r + x;", returns="r: int, s: int")
        self.same_results(ir, "f", [([3], (6, 9))])

    def test_recursive_call(self):
        ir = single("if (x <= 1) {r = 1;} else {r = x * f(x - 1);}")
        self.same_results(ir, "f", [([1], 1), ([5], 120)])

    def test_short_circuit(self):
        ir = single("r = (x != 0 and 12 / x >= 3) or x == 0;", returns="r: bool")
        self.same_results(ir, "f", [([0], True), ([3], True), ([6], False)])
        ir = single("r = x == 0 or 12 / x == 1;", returns="r: bool")
        self.same_results(ir, "f", [([0], True), ([12], True), ([3], False)])

    def test_join_and_reassignment(self):
        ir = single("let y = 4; if (x > 0) {y = 7;} r = y; y = 1; y = x; r = r + y;")
        self.same_results(ir, "f", [([-2], 2), ([3], 10)])

    def test_signed_int(self):
        ir = single("r = -7 / 3; s = 7 / -3; t = 2147483647 + 1; u = t / -1;",
                    returns="r: int, s: int, t: int, u: int")
        self.same_results(ir, "f", [([0], (-2, -2, -(2**31), -(2**31)))])

    def test_switches(self):
        ir = single("let y = 1 + 2; let unused = x * 9; r = (x + 0) - y;")
        self.assertEqual(optimize(ir, False, False, False), ir)
        const = optimize(ir, True, False, False)
        self.assertEqual(ops(const).count("+"), 1)
        minus = next(ins for ins in const["functions"]["f"]["blocks"]["B0"] if ins["op"] == "-")
        self.assertEqual(minus["args"][1], 3)
        algebra = optimize(ir, False, True, False)
        self.assertEqual(ops(algebra).count("+"), 1)
        self.assertIn("*", ops(algebra))
        self.assertNotIn("*", ops(optimize(ir, False, False, True)))
        self.assertEqual(ops(ir).count("+"), 2)

    def test_errors_survive_dce(self):
        programs = [(single("let dead = 1 / 0; r = 8;"), [1], ZeroDivisionError),
                    (single("r = (1 / x) * 0;"), [0], ZeroDivisionError),
                    (single("let dead = a[1]; r = 7;", "a: int[]"), [[]], IndexError),
                    (single("a[x] = 0; r = 3;", "a: int[], x: int"), [[9], -1], IndexError),
                    (compile_source("function g() returns (v: int) {assert false; v = 2;}"
                                    "function f() returns (r: int) {let dead = g(); r = 0;}"),
                     [], AssertionError)]
        for ir, args, error in programs:
            for version in (ir, optimize(ir)):
                with self.subTest(error=error), self.assertRaises(error):
                    run(version, "f", args)

    def test_contract_failure_point(self):
        ir = compile_source("function f(x: int) returns (r: int) requires x >= 0; ensures r < 5;"
                            "{ r = 0; while (r < x) invariant r <= 5; { r = r + 1; } assume x != 2; }")
        for x, kind in ((-1, "requires"), (2, "assume"), (5, "ensures"), (6, "invariant")):
            for version in (ir, optimize(ir)):
                with self.subTest(x=x), self.assertRaisesRegex(AssertionError, kind):
                    run(version, "f", [x])

    def test_cfg_and_loop_liveness(self):
        fn = example("loop")["functions"]["sum"]
        cfg = analyze(fn)["cfg"]
        self.assertEqual(cfg["B0"], ["B1"])
        self.assertEqual(cfg["B1"], ["B2", "B3"])
        self.assertEqual(cfg["B3"], [])
        self.assertEqual(cfg["B5"], ["B1"])
        self.assertEqual(live_out(fn)["B5"], {"v3", "v4", "v5"})
        for code in fn["blocks"].values():
            self.assertIn(code[-1]["op"], {"br", "jmp", "ret"})
            self.assertFalse(any(ins["op"] in {"br", "jmp", "ret"} for ins in code[:-1]))

    def test_conflict_graph_and_reuse(self):
        fn = single("r = (x + 1) * (x - 2);")["functions"]["f"]
        info = analyze(fn)
        self.assertEqual(info["conflicts"], {"t0": ["t1"], "t1": ["t0"], "t2": []})
        self.assertEqual(info["colors"], {"t0": 0, "t1": 1, "t2": 0})
        self.assertEqual(analyze(single("r = x;")["functions"]["f"])["metrics"]["colors"], 0)

    def test_colored_execution_across_blocks(self):
        # Разные имена одного цвета получают один слот прямо в копии IR.
        ir = single("r = (x < 5) == ((x != 0 and 20 / x > 1) or x == 0);", returns="r: bool")
        for version in (ir, optimize(ir)):
            fn = version["functions"]["f"]
            colors = analyze(fn)["colors"]
            slots = {name: f"slot{color}" for name, color in colors.items()}
            for code in fn["blocks"].values():
                for ins in code:
                    ins["args"] = [slots.get(a, a) for a in ins["args"]]
                    if "dest" in ins:
                        ins["dest"] = slots.get(ins["dest"], ins["dest"])
            for x, expected in ((0, True), (2, True), (8, False), (30, True)):
                self.assertEqual(run(version, "f", [x]), expected)

    def test_dead_division_result_needs_own_slot(self):
        ir = single("r = (x + 1) + (12 / x) * 0;")
        # Пока t0 хранит x + 1, деление записывает свой результат в t1.
        fn = optimize(ir)["functions"]["f"]
        info = analyze(fn)
        self.assertIn("t1", info["conflicts"]["t0"])
        self.assertNotEqual(info["colors"]["t0"], info["colors"]["t1"])

    def test_example_output(self):
        for name in ("basic", "branch", "loop"):
            ir = example(name)
            text = format_text({"before": stage(ir), "after": stage(optimize(ir))})
            self.assertEqual(text, (ROOT / "examples" / f"{name}.expected.txt").read_text(encoding="utf-8"))


class CLITests(unittest.TestCase):
    def cli(self, *args, source=None):
        return subprocess.run([sys.executable, str(ROOT / "funny_ir.py"), *args],
                              input=source, text=True, capture_output=True, cwd=ROOT.parent.parent)

    def test_stdin_json_out_and_no_opt(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "ir.json"
            proc = self.cli("-", "--no-opt", "--json", "--out", dest,
                            source="function f() returns (r: int) {r = 1 + 2;}")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "")
            data = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(data["before"], data["after"])
            self.assertEqual(run(data["after"]["ir"], "f", []), 3)

    def test_frontend_error(self):
        proc = self.cli(HW3 / "errors.funny")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("E_TYPE_MISMATCH", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_each_cli_switch(self):
        before = example("basic")
        for flag, disabled in (("--no-const", "constants"), ("--no-simplify", "algebra"),
                               ("--no-dce", "dce")):
            with self.subTest(flag=flag):
                proc = self.cli(ROOT / "examples" / "basic.funny", flag, "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                after = json.loads(proc.stdout)["after"]["ir"]
                self.assertEqual(after, optimize(before, **{disabled: False}))

    def test_missing_file(self):
        self.assertEqual(self.cli(ROOT / "missing.funny").returncode, 2)

    def test_dot_export(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "graphs"
            proc = self.cli(ROOT / "examples" / "loop.funny", "--dot-dir", dest)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            cfg = (dest / "loop.cfg.dot").read_text(encoding="utf-8")
            conflicts = (dest / "loop.conflicts.dot").read_text(encoding="utf-8")
            self.assertIn('before_0_B1 -> before_0_B2 [label="true"];', cfg)
            self.assertIn("after_0_B5 -> after_0_B1;", cfg)
            self.assertIn("before_1_t1 -- before_1_t2;", conflicts)
            self.assertNotIn("after_1_t1 -- after_1_t2;", conflicts)


if __name__ == "__main__":
    unittest.main()
