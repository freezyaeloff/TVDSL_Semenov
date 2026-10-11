"""Корпус тестов HW1: вход, ожидаемый первый токен, пояснение."""

import sys
from pathlib import Path

from funny_lexer import DELIMITERS, KEYWORDS, OPERATORS, build_funny, run_dfa


def corpus():
    cases = [
        ("", None, "пустая строка", False),
        (" \t\r\n", "WS", "только пробелы (skip)", False),
        ("  ", "WS", "несколько пробелов (skip)", False),
        ("// comment", "COMMENT", "комментарий (skip)", False),
        ("//", "COMMENT", "пустой комментарий (skip)", False),
        ("00", "INT", "INT(0) + INT(0), не один INT", True),
        ("01", "INT", "INT(0) + INT(1), не один INT", True),
        ("functio", "IDENT", "префикс keyword -> IDENT", True),
        ("iff", "IDENT", "не keyword -> IDENT", True),
        ("===", "OP", "maximal munch: OP(==) + OP(=)", False),
        ("/ /", "OP", "деление, не COMMENT", True),
        ("1π", "INT", "1 корректно, затем non-ASCII", True),
        ("123abc", "INT", "не IDENT: начинается с цифры", True),
    ]
    for value in ("0", "7", "42", "100"):
        cases.append((value, "INT", "целое число", False))
    for value in ("foo", "_x", "foo_bar", "_1"):
        cases.append((value, "IDENT", "идентификатор", False))
    for word in KEYWORDS:
        cases.extend([
            (word, word.upper(), "ключевое слово", False),
            (word + ";", word.upper(), "ключевое слово перед разделителем", False),
            (word + "x", "IDENT", "более длинный IDENT, не keyword", True),
        ])
    for op in OPERATORS:
        cases.append((op, "OP", "оператор из спецификации", False))
    for delim in DELIMITERS:
        cases.append((delim, "DELIM", "разделитель из спецификации", False))
    for value in ("π", "@", "#", "\x80", "\x00", "\x0b", "!", "&"):
        cases.append((value, None, "не токен -> trap", True))
    return cases


def validate_structure(dfa):
    size = len(dfa.trans)
    assert dfa.trap not in dfa.accept, "Ловушка принимающая"
    assert dfa.trans[dfa.trap] == [dfa.trap] * 128, "Ловушка не замкнута"
    assert sum(i not in dfa.accept and row == [i] * 128
               for i, row in enumerate(dfa.trans)) == 1, "Ловушка не единственная"
    reachable, stack = {dfa.start}, [dfa.start]
    while stack:
        source = stack.pop()
        assert len(dfa.trans[source]) == 128, "Неполная таблица ASCII"
        for target in dfa.trans[source]:
            assert 0 <= target < size, "Несуществующая цель перехода"
            if target not in reachable:
                reachable.add(target)
                stack.append(target)
    assert len(reachable) == size, "Есть недостижимые состояния"


def run_tests(dfa, minimal, report):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    validate_structure(dfa)
    validate_structure(minimal)
    cases = corpus()
    lines = ["# Отчёт о тестах HW1", "",
             "expected/actual — имя первого токена (включая WS/COMMENT) или None.", "",
             "| input | expected | actual | ok | note |",
             "| --- | --- | --- | --- | --- |"]
    failures = 0
    print(f"{'input':<25} {'expected':<10} {'actual':<10} {'ok':<4} note")
    print("-" * 85)
    for text, expected, note, negative in cases:
        actual = run_dfa(minimal, text)
        ok = actual == expected and run_dfa(dfa, text) == expected
        failures += not ok
        status = "PASS" if ok else "FAIL"
        note = ("Отрицательный: " if negative else "") + note
        escaped = repr(text).replace("|", "&#124;")
        lines.append(f"| `{escaped}` | {expected} | {actual} | {status} | {note} |")
        print(f"{text!r:<25} {str(expected):<10} {str(actual):<10} {status:<4} {note}")
    negative_count = sum(case[3] for case in cases)
    lines.extend(["", f"Строк: {len(cases)}; отрицательных: {negative_count}; ошибок: {failures}.", "",
                  "Проверены эквивалентность ДКА до/после минимизации на корпусе, полнота таблиц, достижимость состояний и единственная замкнутая непринимающая ловушка.", "",
                  "ALL PASS" if not failures else "FAIL"])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if failures:
        raise AssertionError(f"Ошибок: {failures}; см. {report}")
    print(f"ALL PASS: {len(cases)} inputs, {negative_count} negative")


if __name__ == "__main__":
    _, dfa, minimal = build_funny()
    run_tests(dfa, minimal, Path(__file__).with_name("tests.md"))
