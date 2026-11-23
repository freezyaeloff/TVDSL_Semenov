def int32(value):
    return (value + 2**31) % 2**32 - 2**31


def variable(node):
    return f"v{node['symbol_id']}"


class Builder:
    def __init__(self):
        self.blocks = {}
        self.types = {}
        self.next_label = 0
        self.next_temp = 0
        self.start(self.label())

    def label(self):
        label = f"B{self.next_label}"
        self.next_label += 1
        return label

    def start(self, label):
        self.code = []
        self.blocks[label] = self.code

    def temp(self, value_type):
        name = f"t{self.next_temp}"
        self.next_temp += 1
        self.types[name] = value_type
        return name

    def declare(self, node):
        name = variable(node)
        self.types[name] = node["declared_type"]
        return name

    def emit(self, op, *args, **fields):
        self.code.append({"op": op, "args": list(args), **fields})

    def jump(self, target):
        self.emit("jmp", targets=[target])

    def expression(self, node):
        kind = node["type"]
        if kind == "Int":
            return int32(node["value"])
        if kind == "Bool":
            return node["value"]
        if kind == "Name":
            return variable(node)

        if kind == "Binary":
            op = node["operator"]
            left = self.expression(node["left"])
            if op in ("and", "or"):
                # Правая часть выполняется только на одном из двух путей.
                result = self.temp(node["inferred_type"])
                rhs, end = self.label(), self.label()
                self.emit("mov", left, dest=result)
                targets = [rhs, end] if op == "and" else [end, rhs]
                self.emit("br", left, targets=targets)
                self.start(rhs)
                self.emit("mov", self.expression(node["right"]), dest=result)
                self.jump(end)
                self.start(end)
                return result
            args = [left, self.expression(node["right"])]
        elif kind == "Unary":
            op = "neg" if node["operator"] == "-" else "not"
            args = [self.expression(node["operand"])]
        elif kind == "Call":
            name = node["function"]["name"]
            args = [self.expression(arg) for arg in node["args"]]
            result = self.temp(node["inferred_type"])
            if name == "length":
                self.emit("length", *args, dest=result)
            else:
                self.emit("call", *args, dest=result, callee=name)
            return result
        elif kind in ("Index", "ArrayUpdate"):
            op = "index" if kind == "Index" else "update"
            args = [self.expression(node["array"]), self.expression(node["index"])]
            if kind == "ArrayUpdate":
                args.append(self.expression(node["value"]))
        else:
            raise ValueError(f"Неизвестное выражение {kind}")

        result = self.temp(node["inferred_type"])
        self.emit(op, *args, dest=result)
        return result

    def check(self, op, node):
        if node is not None:
            self.emit(op, self.expression(node))

    def statement(self, node):
        kind = node["type"]
        if kind == "Block":
            for item in node["statements"]:
                self.statement(item)
        elif kind in ("VarDecl", "Assign"):
            name = self.declare(node) if kind == "VarDecl" else variable(node)
            if node["value"] is not None:
                self.emit("mov", self.expression(node["value"]), dest=name)
        elif kind in ("Assert", "Assume"):
            self.check(kind.lower(), node["expression"])
        elif kind == "If":
            then, end = self.label(), self.label()
            otherwise = self.label() if node["otherwise"] is not None else end
            self.emit("br", self.expression(node["condition"]), targets=[then, otherwise])
            self.start(then)
            self.statement(node["then"])
            self.jump(end)
            if otherwise != end:
                self.start(otherwise)
                self.statement(node["otherwise"])
                self.jump(end)
            self.start(end)
        elif kind == "While":
            head, body, end = self.label(), self.label(), self.label()
            self.jump(head)
            self.start(head)
            for invariant in node["invariants"]:
                self.check("invariant", invariant)
            self.emit("br", self.expression(node["condition"]), targets=[body, end])
            self.start(body)
            self.statement(node["body"])
            self.jump(head)
            self.start(end)
        else:
            raise ValueError(f"Неизвестная инструкция {kind}")

    def function(self, node):
        decls = node["declarations"]
        params = [self.declare(item) for item in decls["params"]]
        results = [self.declare(item) for item in decls["returns"]]
        for item in decls["uses"]:
            self.declare(item)
        for item in node["requires"]:
            self.check("requires", item)
        self.statement(node["body"])
        for item in node["ensures"]:
            self.check("ensures", item)
        self.emit("ret", *results)
        return {"params": params, "returns": results, "types": self.types, "blocks": self.blocks}


def generate(typed_ast):
    if typed_ast["schema_version"] != "funny.typed-ast.v1":
        raise ValueError("Неизвестная версия AST")
    if typed_ast["errors"] or typed_ast["ast"] is None:
        raise ValueError("Для генерации IR нужен AST без ошибок")
    functions = {node["name"]: Builder().function(node) for node in typed_ast["ast"]["functions"]}
    return {"schema_version": "funny.ir.v1", "functions": functions}
