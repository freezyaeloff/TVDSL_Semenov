import operator

from hw4.ir import int32


ARITHMETIC = {"+": operator.add, "-": operator.sub, "*": operator.mul, "neg": operator.neg}
COMPARE = {"==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le,
           ">": operator.gt, ">=": operator.ge, "not": operator.not_}
SCALAR_OPS = set(ARITHMETIC) | set(COMPARE) | {"/"}
CHECKS = {"assert", "assume", "requires", "ensures", "invariant"}


def scalar(op, args):
    if op in ARITHMETIC:
        return int32(ARITHMETIC[op](*args))
    if op == "/":
        left, right = args
        quotient = abs(left) // abs(right)
        return int32(-quotient if (left < 0) != (right < 0) else quotient)
    return COMPARE[op](*args)


def run(program, name, arguments):
    function = program["functions"][name]
    if len(arguments) != len(function["params"]):
        raise ValueError(f"{name}: неверное число аргументов")
    values = dict(zip(function["params"], arguments))
    label = "B0"
    while True:
        for ins in function["blocks"][label]:
            op = ins["op"]
            args = [values[a] if isinstance(a, str) else a for a in ins["args"]]
            if op == "ret":
                if len(args) == 1:
                    return args[0]
                return tuple(args)
            if op == "jmp":
                label = ins["targets"][0]
                break
            if op == "br":
                label = ins["targets"][0 if args[0] else 1]
                break
            if op in CHECKS:
                if not args[0]:
                    raise AssertionError(op)
                continue
            if op == "mov":
                result = args[0]
            elif op in SCALAR_OPS:
                result = scalar(op, args)
            elif op == "call":
                result = run(program, ins["callee"], args)
            elif op == "length":
                result = len(args[0])
            elif op in ("index", "update"):
                array, index = args[:2]
                if not 0 <= index < len(array):
                    raise IndexError(index)
                if op == "index":
                    result = array[index]
                else:
                    result = list(array)
                    result[index] = args[2]
            else:
                raise ValueError(f"Неизвестная операция {op}")
            values[ins["dest"]] = result
