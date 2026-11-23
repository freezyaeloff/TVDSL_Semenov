import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw3.funny_types import check
from hw4.dot import format_dot
from hw4.flow import analyze
from hw4.ir import generate
from hw4.optimize import optimize


def stage(program):
    analysis = {name: analyze(fn) for name, fn in program["functions"].items()}
    return {"ir": program, "analysis": analysis}


def instruction(ins):
    args = [str(a).lower() if isinstance(a, bool) else str(a) for a in ins["args"]]
    if "callee" in ins:
        args.insert(0, ins["callee"])
    args.extend(ins.get("targets", []))
    prefix = ins["dest"] + " = " if "dest" in ins else ""
    return prefix + ins["op"] + (" " + ", ".join(args) if args else "")


def format_text(report):
    lines = []
    for key, title in (("before", "До оптимизаций"), ("after", "После оптимизаций")):
        lines.append(title)
        for name, fn in report[key]["ir"]["functions"].items():
            lines.append(f"function {name}({', '.join(fn['params'])}) returns ({', '.join(fn['returns'])})")
            info = report[key]["analysis"][name]
            variables = ", ".join(v for v in fn["types"] if v.startswith("v"))
            lines.append(f"  Именованные переменные — {variables or '∅'}")
            for label, code in fn["blocks"].items():
                lines.append(f"  {label}:")
                lines.extend("    " + instruction(ins) for ins in code)
            lines.append("  Граф блоков (CFG)")
            for label, targets in info["cfg"].items():
                lines.append(f"    {label} -> {', '.join(targets) or '∅'}")
            lines.append("  Граф конфликтов временных и раскраска")
            if not info["conflicts"]:
                lines.append("    ∅")
            for temp, neighbors in info["conflicts"].items():
                lines.append(f"    {temp} [{info['colors'][temp]}] -> {', '.join(neighbors) or '∅'}")
            stats = info["metrics"]
            lines.append(f"  Состояний CFG (блоков) {stats['blocks']}, "
                         f"инструкций {stats['instructions']}, временных {stats['temporaries']}, "
                         f"цветов {stats['colors']}")
            lines.append("")
    lines.append("Сравнение (до → после)")
    labels = (("blocks", "состояний CFG"), ("instructions", "инструкций"),
              ("temporaries", "временных"), ("colors", "цветов"))
    for name, info in report["before"]["analysis"].items():
        before = info["metrics"]
        after = report["after"]["analysis"][name]["metrics"]
        changes = ", ".join(f"{label} {before[key]} → {after[key]}" for key, label in labels)
        lines.append(f"  {name} — {changes}")
    lines.append("")
    return "\n".join(lines)


def main():
    cli = argparse.ArgumentParser(description="Генерация и оптимизация IR Funny (HW4)")
    cli.add_argument("source", type=Path, help="исходный файл Funny или - для stdin")
    cli.add_argument("--no-opt", action="store_true", help="отключить все оптимизации")
    cli.add_argument("--no-const", action="store_true",
                     help="отключить свёртку констант и удаление недостижимых ветвей")
    cli.add_argument("--no-simplify", action="store_true", help="отключить алгебраические упрощения")
    cli.add_argument("--no-dce", action="store_true", help="отключить удаление мёртвых инструкций")
    cli.add_argument("--json", action="store_true", help="вывести IR и графы в JSON")
    cli.add_argument("--out", type=Path, help="сохранить вывод в файл")
    cli.add_argument("--dot-dir", type=Path, help="сохранить графы до и после оптимизации в папку")
    args = cli.parse_args()
    try:
        source = sys.stdin.read() if str(args.source) == "-" else args.source.read_text(encoding="utf-8-sig")
        typed_ast = check(source)
        if typed_ast["errors"]:
            for err in typed_ast["errors"]:
                print(f"{err['line']}:{err['column']}: {err['code']}: {err['message']}", file=sys.stderr)
            return 1
        before = generate(typed_ast)
        after = optimize(before, constants=not (args.no_opt or args.no_const),
                         algebra=not (args.no_opt or args.no_simplify),
                         dce=not (args.no_opt or args.no_dce))
        report = {"before": stage(before), "after": stage(after)}
        if args.dot_dir is not None:
            args.dot_dir.mkdir(parents=True, exist_ok=True)
            stem = "stdin" if str(args.source) == "-" else args.source.stem
            for kind in ("cfg", "conflicts"):
                path = args.dot_dir / f"{stem}.{kind}.dot"
                path.write_text(format_dot(report, kind), encoding="utf-8")
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.json else format_text(report)
        if args.out:
            args.out.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    except (OSError, UnicodeError) as error:
        print(f"Ошибка ввода/вывода: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
