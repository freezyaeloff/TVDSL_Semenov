from copy import deepcopy

from hw4.flow import live_out, reads, successors, temporaries
from hw4.interpreter import SCALAR_OPS, scalar


def simplify(op, args):
    if len(args) != 2:
        return None
    a, b = args
    if op == "+" and a == 0:
        return b
    if op in ("+", "-") and b == 0:
        return a
    if op == "*" and (a == 0 or b == 0):
        return 0
    if op == "*" and a == 1:
        return b
    if op in ("*", "/") and b == 1:
        return a
    if op == "-" and a == b:
        return 0
    return None


def rewrite(code, constants, algebra):
    known = {}
    for ins in code:
        op, args = ins["op"], ins["args"]
        if constants:
            args = [known.get(a, a) for a in args]
            ins["args"] = args
            if op == "br" and isinstance(args[0], bool):
                target = ins["targets"][0 if args[0] else 1]
                ins.update(op="jmp", args=[], targets=[target])
        dest = ins.get("dest")
        if dest is None:
            continue

        replacement = None
        if constants and op in SCALAR_OPS and all(not isinstance(a, str) for a in args):
            if op != "/" or args[1] != 0:
                replacement = scalar(op, args)
        if replacement is None and algebra:
            replacement = simplify(op, args)
        if replacement is not None:
            ins["op"], ins["args"] = "mov", [replacement]

        known.pop(dest, None)
        if constants and ins["op"] == "mov" and not isinstance(ins["args"][0], str):
            known[dest] = ins["args"][0]


def remove_unreachable(function):
    edges = successors(function)
    reachable = set()
    pending = ["B0"]
    while pending:
        label = pending.pop()
        if label not in reachable:
            reachable.add(label)
            pending.extend(edges[label])
    function["blocks"] = {label: code for label, code in function["blocks"].items()
                          if label in reachable}


def remove_dead(function):
    out = live_out(function)
    removable = (SCALAR_OPS - {"/"}) | {"mov"}
    for label, code in function["blocks"].items():
        live = out[label].copy()
        kept = []
        for ins in reversed(code):
            dest = ins.get("dest")
            if ins["op"] in removable and dest not in live:
                continue
            live.discard(dest)
            live.update(reads(ins))
            kept.append(ins)
        function["blocks"][label] = list(reversed(kept))


def optimize(program, constants=True, algebra=True, dce=True):
    result = deepcopy(program)
    for function in result["functions"].values():
        for code in function["blocks"].values():
            rewrite(code, constants, algebra)
        if constants:
            remove_unreachable(function)
        if dce:
            remove_dead(function)
        temps = temporaries(function)
        function["types"] = {name: typ for name, typ in function["types"].items()
                             if not name.startswith("t") or name in temps}
    return result
