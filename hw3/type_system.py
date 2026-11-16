"""Structural monomorphic types and unification with occurs check and rollback."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Type:
    kind: str
    args: tuple = ()


@dataclass(eq=False)
class TypeVar:
    binding: object = None


INT, BOOL, UNIT, ERROR = (Type(name) for name in ("int", "bool", "unit", "error"))


def array(element):
    return Type("array", (element,))


def function(params, result):
    return Type("func", (*params, result))


def product(items):
    items = tuple(items)
    return UNIT if not items else items[0] if len(items) == 1 else Type("tuple", items)


def resolve(value):
    while isinstance(value, TypeVar) and value.binding is not None:
        value = value.binding
    return value


def occurs(variable, value):
    value = resolve(value)
    return value is variable or (isinstance(value, Type) and
                                 any(occurs(variable, child) for child in value.args))


def unify(left, right):
    """Unify atomically: a failed constraint leaves no partial substitutions."""
    trail = []

    def visit(a, b):
        a, b = resolve(a), resolve(b)
        if a is b or a == ERROR or b == ERROR:
            return True
        if isinstance(b, TypeVar) and not isinstance(a, TypeVar):
            a, b = b, a
        if isinstance(a, TypeVar):
            if occurs(a, b):
                return False
            trail.append((a, a.binding))
            a.binding = b
            return True
        return (a.kind == b.kind and len(a.args) == len(b.args) and
                all(visit(x, y) for x, y in zip(a.args, b.args)))

    success = visit(left, right)
    if not success:
        for variable, binding in reversed(trail):
            variable.binding = binding
    return success


def concrete(value):
    value = resolve(value)
    return (isinstance(value, Type) and value != ERROR and
            all(concrete(child) for child in value.args))


def display(value):
    value = resolve(value)
    if isinstance(value, TypeVar):
        return "?"
    if value.kind == "array":
        child = display(value.args[0])
        element = resolve(value.args[0])
        return f"({child})[]" if isinstance(element, Type) and element.kind == "func" else f"{child}[]"
    if value.kind == "func":
        return f"func({', '.join(map(display, value.args[:-1]))}):{display(value.args[-1])}"
    if value.kind == "tuple":
        return f"({', '.join(map(display, value.args))})"
    return value.kind


def encode(value):
    """JSON type schema: primitives as strings, composite types as objects."""
    value = resolve(value)
    if isinstance(value, TypeVar):
        return "error"
    if value.kind == "array":
        return {"kind": "array", "element": encode(value.args[0])}
    if value.kind == "func":
        return {"kind": "func", "params": [encode(t) for t in value.args[:-1]],
                "returns": encode(value.args[-1])}
    if value.kind == "tuple":
        return {"kind": "tuple", "items": [encode(t) for t in value.args]}
    return value.kind
