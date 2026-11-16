"""Name resolution, type checking, local inference and JSON annotated AST for Funny."""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw3.funny_frontend import ParseError, parse
from hw3.type_system import (BOOL, ERROR, INT, Type, TypeVar, array, concrete,
                             display, encode, function, product, resolve, unify)


@dataclass
class Symbol:
    id: int
    name: str
    kind: str
    value_type: object
    scope_id: int
    declaration: dict


@dataclass
class Scope:
    id: int
    parent: object = None
    symbols: dict = field(default_factory=dict)

    def lookup(self, name):
        scope = self
        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        return None


class Analyzer:
    def __init__(self):
        self.errors = []
        self.symbols = []
        self.next_scope = 0
        self.global_scope = self.scope()

    def scope(self, parent=None):
        result = Scope(self.next_scope, parent)
        self.next_scope += 1
        return result

    def error(self, where, code, message):
        self.errors.append({"phase": "semantic", "code": code,
                            "line": where["line"], "column": where["column"],
                            "message": message})

    def declare(self, scope, declaration, kind, value_type):
        name = declaration["name"]
        if name in scope.symbols:
            previous = scope.symbols[name].declaration
            self.error(declaration, "E_DUPLICATE",
                       f"повторное объявление '{name}'; первое: "
                       f"{previous['line']}:{previous['column']}")
            return None
        symbol = Symbol(len(self.symbols), name, kind, value_type, scope.id, declaration)
        scope.symbols[name] = symbol
        self.symbols.append(symbol)
        declaration["symbol_id"] = symbol.id
        declaration["declared_type"] = value_type
        return symbol

    def annotation(self, annotation):
        kind = annotation["type"]
        if kind == "TypeName":
            result = {"int": INT, "bool": BOOL}.get(annotation["name"])
            if result is None:
                self.error(annotation, "E_TYPE_UNKNOWN",
                           f"неизвестный тип '{annotation['name']}'")
                return ERROR
            return result
        if kind == "ArrayType":
            return array(self.annotation(annotation["element"]))
        raise ValueError(f"Unknown annotation node: {kind}")

    def declaration_type(self, declaration, required=False):
        if declaration["annotation"] is not None:
            result = self.annotation(declaration["annotation"])
        elif required:
            self.error(declaration, "E_ANNOTATION_REQUIRED",
                       f"для '{declaration['name']}' требуется явная аннотация типа")
            result = ERROR
        else:
            result = TypeVar()
        declaration["declared_type"] = result
        return result

    def expect_type(self, actual, expected, where, context):
        if not unify(actual, expected):
            self.error(where, "E_TYPE_MISMATCH",
                       f"{context}: ожидался {display(expected)}, получен {display(actual)}")
            return False
        return concrete(actual) and concrete(expected)

    def name(self, expression, scope, assigned, as_callee=False):
        symbol = scope.lookup(expression["name"])
        if symbol is None:
            self.error(expression, "E_UNKNOWN_NAME",
                       f"имя '{expression['name']}' не объявлено или использовано до объявления")
            return ERROR
        expression["symbol_id"] = symbol.id
        if symbol.kind == "builtin":
            self.error(expression, "E_BUILTIN_VALUE", "length допускается только в прямом вызове")
            return ERROR
        if symbol.kind == "function" and not as_callee:
            self.error(expression, "E_FUNCTION_VALUE",
                       f"функция '{symbol.name}' допускается только в вызове")
            return ERROR
        if symbol.kind != "function" and symbol.id not in assigned:
            self.error(expression, "E_UNINITIALIZED",
                       f"'{symbol.name}' используется до корректного присваивания")
            return ERROR
        return symbol.value_type

    def expression(self, expression, scope, assigned, as_callee=False):
        kind = expression["type"]
        result = ERROR
        if kind in ("Int", "Bool"):
            result = INT if kind == "Int" else BOOL
        elif kind == "Name":
            result = self.name(expression, scope, assigned, as_callee)
        elif kind == "Unary":
            operand = self.expression(expression["operand"], scope, assigned)
            expected = BOOL if expression["operator"] == "not" else INT
            if self.expect_type(operand, expected, expression, "унарный оператор"):
                result = expected
        elif kind == "Binary":
            left = self.expression(expression["left"], scope, assigned)
            right = self.expression(expression["right"], scope, assigned)
            operator = expression["operator"]
            if operator in ("==", "!="):
                good = self.expect_type(right, left, expression, "сравнение на равенство")
                if good and resolve(left) not in (INT, BOOL):
                    self.error(expression, "E_EQUALITY_TYPE",
                               "равенство поддерживается только для int и bool")
                elif good:
                    result = BOOL
            else:
                expected = BOOL if operator in ("and", "or") else INT
                good_left = self.expect_type(left, expected, expression["left"],
                                             f"левый операнд '{operator}'")
                good_right = self.expect_type(right, expected, expression["right"],
                                              f"правый операнд '{operator}'")
                if good_left and good_right:
                    result = BOOL if operator in ("and", "or", "<", "<=", ">", ">=") else INT
        elif kind == "Call":
            result = self.call(expression, scope, assigned)
        elif kind in ("Index", "ArrayUpdate"):
            base = self.expression(expression["array"], scope, assigned)
            index = self.expression(expression["index"], scope, assigned)
            good = self.expect_type(index, INT, expression["index"], "индекс массива")
            base = resolve(base)
            if isinstance(base, Type) and base.kind == "array":
                if kind == "ArrayUpdate":
                    value = self.expression(expression["value"], scope, assigned)
                    good_value = self.expect_type(value, base.args[0], expression["value"],
                                                  "элемент массива")
                    if good and good_value and concrete(base):
                        result = base
                elif good and concrete(base):
                    result = base.args[0]
            else:
                if concrete(base):
                    self.error(expression["array"], "E_NOT_ARRAY",
                               f"индексация требует массив, получен {display(base)}")
                if kind == "ArrayUpdate":
                    self.expression(expression["value"], scope, assigned)
        else:
            raise ValueError(f"Unknown expression node: {kind}")
        expression["inferred_type"] = result
        return result

    def call(self, expression, scope, assigned):
        callee = expression["function"]
        symbol = scope.lookup(callee["name"]) if callee["type"] == "Name" else None
        if symbol is not None and symbol.kind == "builtin":
            callee["symbol_id"] = symbol.id
            callee_type = function([array(TypeVar())], INT)
            callee["inferred_type"] = callee_type
        else:
            callee_type = self.expression(callee, scope, assigned, as_callee=True)
        arguments = [self.expression(a, scope, assigned) for a in expression["args"]]
        callee_type = resolve(callee_type)
        if not isinstance(callee_type, Type) or callee_type.kind != "func":
            if concrete(callee_type):
                self.error(callee, "E_NOT_CALLABLE",
                           f"вызов требует функцию, получен {display(callee_type)}")
            return ERROR
        params, result = callee_type.args[:-1], callee_type.args[-1]
        good = len(arguments) == len(params)
        if not good:
            self.error(expression, "E_ARGUMENT_COUNT",
                       f"неверное число аргументов: ожидалось {len(params)}, "
                       f"получено {len(arguments)}")
        for index, (actual, expected) in enumerate(zip(arguments, params), 1):
            matches = self.expect_type(actual, expected, expression["args"][index - 1],
                                       f"аргумент {index}")
            good = good and matches
        if symbol is not None and symbol.kind == "builtin" and not concrete(callee_type):
            callee["inferred_type"] = ERROR
        return result if good and concrete(result) else ERROR

    def assign(self, symbol, value_type, where, assigned):
        
        if symbol.kind in ("function", "builtin"):
            self.error(where, "E_ASSIGN_FUNCTION", f"нельзя присваивать функции '{symbol.name}'")
        elif concrete(value_type):
            if self.expect_type(value_type, symbol.value_type, where,
                                f"присваивание '{symbol.name}'"):
                assigned.add(symbol.id)

    def statement(self, statement, scope, assigned):
        kind = statement["type"]
        if kind == "Block":
            nested = self.scope(scope)
            self.block(statement, nested, assigned)
            assigned.difference_update(s.id for s in nested.symbols.values())
        elif kind == "VarDecl":
            value_type = self.declaration_type(statement)
            symbol = self.declare(scope, statement, "local", value_type)
            if statement["value"] is not None:
                actual = self.expression(statement["value"], scope, assigned)
                if symbol is not None:
                    self.assign(symbol, actual, statement, assigned)
        elif kind == "Assign":
            symbol = scope.lookup(statement["target"])
            if symbol is None:
                self.error(statement, "E_UNKNOWN_NAME",
                           f"имя '{statement['target']}' не объявлено или использовано до объявления")
            actual = self.expression(statement["value"], scope, assigned)
            if symbol is not None:
                statement["symbol_id"] = symbol.id
                self.assign(symbol, actual, statement, assigned)
        elif kind in ("Assert", "Assume"):
            self.predicate(statement["expression"], scope, assigned, kind.lower())
        elif kind == "If":
            self.predicate(statement["condition"], scope, assigned, "условие if")
            then, otherwise = assigned.copy(), assigned.copy()
            self.statement(statement["then"], scope, then)
            if statement["otherwise"] is not None:
                self.statement(statement["otherwise"], scope, otherwise)
            assigned.clear()
            assigned.update(then & otherwise)
        elif kind == "While":
            self.predicate(statement["condition"], scope, assigned, "условие while")
            for invariant in statement["invariants"]:
                self.predicate(invariant, scope, assigned, "инвариант")
            
            self.statement(statement["body"], scope, assigned.copy())
        else:
            raise ValueError(f"Unknown statement node: {kind}")

    def block(self, block, scope, assigned):
        block["scope_id"] = scope.id
        for statement in block["statements"]:
            self.statement(statement, scope, assigned)

    def predicate(self, expression, scope, assigned, context):
        if expression is not None:
            actual = self.expression(expression, scope, assigned)
            self.expect_type(actual, BOOL, expression, context)

    def check_function(self, declaration):
        scope = self.scope(self.global_scope)
        declaration["scope_id"] = scope.id
        assigned = set()
        outputs = []
        for group, kind in (("params", "parameter"), ("returns", "result"), ("uses", "local")):
            for item in declaration["declarations"][group]:
                value_type = item["declared_type"] if group != "uses" else self.declaration_type(item)
                symbol = self.declare(scope, item, kind, value_type)
                if symbol is not None:
                    if kind == "parameter":
                        assigned.add(symbol.id)
                    elif kind == "result":
                        outputs.append(symbol)
        
        for expression in declaration["requires"]:
            self.predicate(expression, scope, assigned, "requires")
        self.block(declaration["body"], scope, assigned)
        for symbol in outputs:
            if symbol.id not in assigned:
                self.error(symbol.declaration, "E_RESULT_UNASSIGNED",
                           f"результат '{symbol.name}' не присвоен на всех путях выполнения")
        
        
        post_assigned = assigned | {s.id for s in outputs}
        for expression in declaration["ensures"]:
            self.predicate(expression, scope, post_assigned, "ensures")

    def analyze(self, tree):
        builtin = {"name": "length", "line": 1, "column": 1}
        self.declare(self.global_scope, builtin, "builtin", Type("builtin_length"))
        
        for declaration in tree["functions"]:
            groups = declaration["declarations"]
            params = [self.declaration_type(d, required=True) for d in groups["params"]]
            results = [self.declaration_type(d, required=True) for d in groups["returns"]]
            signature = function(params, product(results))
            name_declaration = {**declaration["name_position"], "name": declaration["name"]}
            symbol = self.declare(self.global_scope, name_declaration, "function", signature)
            declaration["signature"] = signature
            if symbol is not None:
                declaration["symbol_id"] = symbol.id
        for declaration in tree["functions"]:
            self.check_function(declaration)
        for symbol in self.symbols:
            if symbol.kind == "local" and isinstance(resolve(symbol.value_type), TypeVar):
                self.error(symbol.declaration, "E_CANNOT_INFER",
                           f"невозможно вывести тип '{symbol.name}': нет корректного присваивания")
        symbols = [{"id": s.id, "name": s.name, "kind": s.kind, "scope_id": s.scope_id,
                    "line": s.declaration["line"], "column": s.declaration["column"],
                    "value_type": ("builtin length(array<T>):int" if s.kind == "builtin"
                                   else encode(s.value_type))} for s in self.symbols]
        self.encode_tree(tree)
        return {"schema_version": "funny.typed-ast.v1", "ast": tree,
                "symbols": symbols, "errors": self.errors}

    @classmethod
    def encode_tree(cls, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (Type, TypeVar)):
                    value[key] = encode(item)
                else:
                    cls.encode_tree(item)
        elif isinstance(value, list):
            for item in value:
                cls.encode_tree(item)


def frontend_error(message, phase):
    match = re.match(r"(\d+):(\d+):\s*(.*)", message, re.DOTALL)
    return {"phase": phase, "code": "E_LEXICAL" if phase == "lexical" else "E_SYNTAX",
            "line": int(match[1]) if match else 1,
            "column": int(match[2]) if match else 1,
            "message": match[3] if match else message}


def check(source):
    """Return a JSON-compatible result; never reuse state between programs."""
    try:
        tree, errors = parse(source)
    except ParseError as error:
        return {"schema_version": "funny.typed-ast.v1", "ast": None, "symbols": [],
                "errors": [frontend_error(str(error), "lexical")]}
    result = Analyzer().analyze(tree)
    result["errors"] = [frontend_error(e, "syntax") for e in errors] + result["errors"]
    return result


def main():
    cli = argparse.ArgumentParser(description="Семантический анализатор Funny (HW3)")
    cli.add_argument("source", type=Path, help="файл Funny; '-' означает stdin")
    cli.add_argument("--out", type=Path, help="сохранить JSON AST и диагностику")
    args = cli.parse_args()
    try:
        source = sys.stdin.read() if str(args.source) == "-" else args.source.read_text(encoding="utf-8-sig")
        result = check(source)
        output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    except (OSError, UnicodeError) as error:
        print(f"Ошибка ввода/вывода: {error}", file=sys.stderr)
        return 2
    for error in result["errors"]:
        print(f"{error['line']}:{error['column']}: {error['code']}: {error['message']}", file=sys.stderr)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
