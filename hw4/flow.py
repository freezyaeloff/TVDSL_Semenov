def reads(ins):
    return {arg for arg in ins["args"] if isinstance(arg, str)}


def successors(function):
    return {label: code[-1].get("targets", []) for label, code in function["blocks"].items()}


def live_out(function):
    blocks = function["blocks"]
    edges = successors(function)
    uses, defs = {}, {}
    for label, code in blocks.items():
        used, defined = set(), set()
        for ins in code:
            used.update(reads(ins) - defined)
            if "dest" in ins:
                defined.add(ins["dest"])
        uses[label], defs[label] = used, defined

    entry = {label: set() for label in blocks}
    out = {label: set() for label in blocks}
    changed = True
    while changed:
        changed = False
        for label in reversed(blocks):
            out[label] = set().union(*(entry[target] for target in edges[label]))
            new = uses[label] | (out[label] - defs[label])
            if entry[label] != new:
                entry[label] = new
                changed = True
    return out


def temporaries(function):
    names = set()
    for code in function["blocks"].values():
        for ins in code:
            names.update(reads(ins))
            if "dest" in ins:
                names.add(ins["dest"])
    return {name for name in names if name.startswith("t")}


def allocate(function):
    temps = temporaries(function)
    graph = {name: set() for name in sorted(temps)}
    out = live_out(function)
    for label, code in function["blocks"].items():
        live = out[label] & temps
        for ins in reversed(code):
            dest = ins.get("dest")
            if dest in temps:
                live.discard(dest)
                for name in live:
                    graph[dest].add(name)
                    graph[name].add(dest)
            live.update(reads(ins) & temps)

    colors = {}
    for name in sorted(graph, key=lambda t: (-len(graph[t]), int(t[1:]))):
        taken = {colors[other] for other in graph[name] if other in colors}
        color = 0
        while color in taken:
            color += 1
        colors[name] = color
    return {t: sorted(neighbors) for t, neighbors in graph.items()}, colors


def analyze(function):
    graph, colors = allocate(function)
    blocks = function["blocks"]
    metrics = {"blocks": len(blocks), "instructions": sum(map(len, blocks.values())),
               "temporaries": len(graph), "colors": len(set(colors.values()))}
    return {"cfg": successors(function), "conflicts": graph, "colors": colors, "metrics": metrics}
