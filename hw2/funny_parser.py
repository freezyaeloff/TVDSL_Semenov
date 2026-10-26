import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

from dataclasses import dataclass


@dataclass
class DFA:
    trans: list
    accept: dict
    start: int
    trap: int


def step(dfa, state, symbol):
    code = ord(symbol)
    return dfa.trans[state][code] if code < 128 else dfa.trap


@lru_cache(maxsize=1)
def load_dfa():
    data = json.loads(Path(__file__).with_name("dfa.json").read_text(encoding="utf-8"))
    transitions = data["trans"]
    return DFA(
        trans=[[transitions[f"{state}|{chr(code)}"] for code in range(128)]
               for state in range(data["n_states"])],
        accept={int(state): (item["token"], item["skip"])
                for state, item in data["accept"].items()},
        start=data["start"],
        trap=data["trap"],
    )


class Token:
    def __init__(self, kind, text, line, column):
        self.kind = kind
        self.text = text
        self.line = line
        self.column = column

    def __repr__(self):
        return f"{self.kind}({self.text!r}) at {self.line}:{self.column}"


class ParseError(Exception):
    pass


def tokenize(source):
    dfa = load_dfa()
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    tokens = []
    pos, line, column = 0, 1, 1

    while pos < len(source):
        state = dfa.start
        best = None
        index = pos

        while index < len(source):
            state = step(dfa, state, source[index])
            if state == dfa.trap:
                break
            index += 1
            if state in dfa.accept:
                kind, skip = dfa.accept[state]
                best = (index, kind, skip)

        if best is None:
            raise ParseError(f"{line}:{column}: неизвестный символ {source[pos]!r}")

        end, kind, skip = best
        text = source[pos:end]
        if not skip:
            if kind == "IDENT" and text in ("requires", "ensures"):
                kind = text.upper()
            if kind in ("OP", "DELIM"):
                kind = text
            tokens.append(Token(kind, text, line, column))

        lines = text.split("\n")
        if len(lines) > 1:
            line += len(lines) - 1
            column = len(lines[-1]) + 1
        else:
            column += len(text)
        pos = end

    tokens.append(Token("EOF", "", line, column))
    return tokens


def node(kind, token, **fields):
    return {"type": kind, "line": token.line, "column": token.column, **fields}


PRECEDENCE = {
    "OR": 1,
    "AND": 2,
    "==": 3, "!=": 3,
    "<": 4, "<=": 4, ">": 4, ">=": 4,
    "+": 5, "-": 5,
    "*": 6, "/": 6,
}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    @property
    def current(self):
        return self.tokens[self.pos]

    def at(self, *kinds):
        return self.current.kind in kinds

    def take(self):
        token = self.current
        if not self.at("EOF"):
            self.pos += 1
        return token

    def match(self, kind):
        if self.at(kind):
            return self.take()
        return None

    def expect(self, kind):
        if not self.at(kind):
            found = self.current.text or "конец файла"
            raise ParseError(f"{self.current.line}:{self.current.column}: "
                             f"ожидалось {kind}, получено {found!r}")
        return self.take()

    def synchronize(self):
        """Режим паники: пропустить ошибочную инструкцию до ; или }."""
        while not self.at(";", "}", "EOF", "FUNCTION"):
            self.take()
        self.match(";")

    def program(self):
        functions = []
        start = self.current
        if self.at("EOF"):
            self.errors.append(f"{start.line}:{start.column}: пустая программа")

        while not self.at("EOF"):
            if not self.at("FUNCTION"):
                self.errors.append(f"{self.current.line}:{self.current.column}: "
                                   "ожидалось объявление function")
                while not self.at("FUNCTION", "EOF"):
                    self.take()
                continue
            try:
                functions.append(self.function())
            except ParseError as error:
                self.errors.append(str(error))
                while not self.at("FUNCTION", "EOF"):
                    self.take()

        return node("Program", start, functions=functions)

    def names(self):
        self.expect("(")
        result = []
        if not self.at(")"):
            result.append(self.expect("IDENT").text)
            while self.match(","):
                result.append(self.expect("IDENT").text)
        self.expect(")")
        return result

    def function(self):
        start = self.expect("FUNCTION")
        name = self.expect("IDENT").text
        params = self.names()
        self.expect("RETURNS")
        returns = self.names()
        uses = self.names() if self.match("USES") else []
        requires, ensures = [], []
        while self.at("REQUIRES", "ENSURES"):
            keyword = self.take()
            expression = None if self.at(";") else self.expression()
            self.expect(";")
            if keyword.kind == "REQUIRES":
                requires.append(expression)
            else:
                ensures.append(expression)
        body = self.block()
        return node("Function", start, name=name, params=params, returns=returns,
                    uses=uses, requires=requires, ensures=ensures, body=body)

    def block(self):
        start = self.expect("{")
        statements = []
        while not self.at("}", "EOF", "FUNCTION"):
            try:
                statements.append(self.statement())
            except ParseError as error:
                self.errors.append(str(error))
                self.synchronize()
        self.expect("}")
        return node("Block", start, statements=statements)

    def statement(self):
        if self.at("{"):
            return self.block()
        if self.at("IF"):
            start = self.take()
            self.expect("(")
            condition = self.expression()
            self.expect(")")
            then = self.block()
            otherwise = None
            if self.match("ELSE"):
                otherwise = self.statement() if self.at("IF") else self.block()
            return node("If", start, condition=condition, then=then, otherwise=otherwise)
        if self.at("WHILE"):
            start = self.take()
            self.expect("(")
            condition = self.expression()
            self.expect(")")
            invariants = []
            while self.match("INVARIANT"):
                invariants.append(self.expression())
                self.expect(";")
            return node("While", start, condition=condition,
                        invariants=invariants, body=self.block())
        if self.at("ASSERT", "ASSUME"):
            start = self.take()
            value = self.expression()
            self.expect(";")
            return node(start.kind.title(), start, expression=value)
        if self.at("IDENT"):
            start = self.take()
            index = None
            if self.match("["):
                index = self.expression()
                self.expect("]")
            self.expect("=")
            value = self.expression()
            self.expect(";")
            if index is not None:
                # a[i] = x  ==>  a = update(a, i, x)
                value = node("ArrayUpdate", start,
                             array=node("Name", start, name=start.text),
                             index=index, value=value)
            return node("Assign", start, target=start.text, value=value)

        found = self.current.text or "конец файла"
        raise ParseError(f"{self.current.line}:{self.current.column}: "
                         f"неожиданный токен {found!r} в инструкции")

    def expression(self, min_precedence=1):
        left = self.unary()
        while PRECEDENCE.get(self.current.kind, 0) >= min_precedence:
            op = self.take()
            right = self.expression(PRECEDENCE[op.kind] + 1)
            left = node("Binary", op, operator=op.text, left=left, right=right)
        return left

    def unary(self):
        if self.at("NOT", "-"):
            op = self.take()
            return node("Unary", op, operator=op.text, operand=self.unary())
        return self.postfix()

    def postfix(self):
        result = self.primary()
        while self.at("[", "("):
            if self.at("["):
                start = self.take()
                index = self.expression()
                self.expect("]")
                result = node("Index", start, array=result, index=index)
            else:
                start = self.take()
                args = []
                if not self.at(")"):
                    args.append(self.expression())
                    while self.match(","):
                        args.append(self.expression())
                self.expect(")")
                result = node("Call", start, function=result, args=args)
        return result

    def primary(self):
        start = self.current
        if self.at("INT"):
            return node("Int", self.take(), value=int(start.text))
        if self.at("TRUE", "FALSE"):
            return node("Bool", self.take(), value=start.kind == "TRUE")
        if self.at("IDENT", "LENGTH"):
            return node("Name", self.take(), name=start.text)
        if self.match("("):
            value = self.expression()
            self.expect(")")
            return value
        raise ParseError(f"{start.line}:{start.column}: "
                         f"ожидалось выражение, получено {start.text or 'конец файла'!r}")


def parse(source):
    parser = Parser(tokenize(source))
    tree = parser.program()
    return tree, parser.errors


def main():
    cli = argparse.ArgumentParser(description="Парсер языка Funny (HW2)")
    cli.add_argument("source", type=Path, nargs="?", help="файл программы Funny")
    cli.add_argument("--out", type=Path, help="путь для JSON AST (без опции печатается в консоль)")
    cli.add_argument("--tests", action="store_true", help="запустить тесты и сохранить tests.md")
    args = cli.parse_args()
    if args.tests:
        from test_parser import run_tests
        if not run_tests():
            raise SystemExit(1)
    if args.source is None:
        if args.tests:
            return
        cli.error("укажите файл программы или --tests")
    try:
        tree, errors = parse(args.source.read_text(encoding="utf-8"))
    except ParseError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        raise SystemExit(1) from None

    result = json.dumps(tree, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
    for error in errors:
        print(f"Ошибка: {error}", file=sys.stderr)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
