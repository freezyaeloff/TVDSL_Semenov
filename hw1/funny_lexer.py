
import argparse
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


ASCII = tuple(chr(i) for i in range(128))


@dataclass(frozen=True)
class Node:
    kind: str
    args: tuple = ()


def char(c):
    if len(c) != 1 or c not in ASCII:
        raise ValueError("Ожидался один ASCII-символ")
    return Node("char", (c,))


def char_class(chars):
    chars = frozenset(chars)
    if not chars <= set(ASCII):
        raise ValueError("Класс должен содержать только ASCII")
    return Node("class", (chars,))


def cat(*nodes):
    return Node("cat", nodes)


def alt(*nodes):
    return Node("alt", nodes)


def star(node):
    return Node("star", (node,))


def plus(node):
    return Node("plus", (node,))


def opt(node):
    return Node("opt", (node,))


def literal(text):
    return cat(*(char(c) for c in text))


@dataclass
class NFA:
    trans: list = field(default_factory=list)
    accept: dict = field(default_factory=dict)
    start: int = 0

    def state(self):
        self.trans.append(defaultdict(set))
        return len(self.trans) - 1

    def edge(self, source, symbol, target):
        self.trans[source][symbol].add(target)


def build(node, nfa):
    kind, args = node.kind, node.args
    if kind in ("char", "class"):
        start, end = nfa.state(), nfa.state()
        symbols = args if kind == "char" else args[0]
        for symbol in symbols:
            nfa.edge(start, symbol, end)
        return start, end
    if kind == "cat" and args:
        start, end = build(args[0], nfa)
        for child in args[1:]:
            next_start, next_end = build(child, nfa)
            nfa.edge(end, None, next_start)
            end = next_end
        return start, end
    start, end = nfa.state(), nfa.state()
    if kind == "cat":
        nfa.edge(start, None, end)
    elif kind == "alt":
        for child in args:
            child_start, child_end = build(child, nfa)
            nfa.edge(start, None, child_start)
            nfa.edge(child_end, None, end)
    elif kind in ("star", "plus", "opt"):
        child_start, child_end = build(args[0], nfa)
        nfa.edge(start, None, child_start)
        nfa.edge(child_end, None, end)
        if kind in ("star", "opt"):
            nfa.edge(start, None, end)
        if kind in ("star", "plus"):
            nfa.edge(child_end, None, child_start)
    else:
        raise ValueError(f"Неизвестный узел AST: {kind}")
    return start, end


def combine(rules):
    nfa = NFA()
    nfa.start = nfa.state()
    for priority, (_, _, node) in enumerate(rules):
        start, end = build(node, nfa)
        nfa.edge(nfa.start, None, start)
        nfa.accept[end] = priority
    return nfa


def epsilon_closure(nfa, states):
    result = set(states)
    stack = list(result)
    while stack:
        state = stack.pop()
        for target in nfa.trans[state].get(None, ()):
            if target not in result:
                result.add(target)
                stack.append(target)
    return frozenset(result)


def move(nfa, states, symbol):
    return {target for state in states
            for target in nfa.trans[state].get(symbol, ())}


@dataclass
class DFA:
    trans: list
    accept: dict
    start: int
    trap: int


def subset_construction(nfa, rules):
    first = epsilon_closure(nfa, {nfa.start})
    ids = {first: 0}
    queue = deque([first])
    trans, accept = [], {}
    while queue:
        states = queue.popleft()
        state_id = ids[states]
        priorities = [nfa.accept[s] for s in states if s in nfa.accept]
        if priorities:
            name, skip, _ = rules[min(priorities)]
            accept[state_id] = (name, skip)
        row = []
        for symbol in ASCII:
            target = epsilon_closure(nfa, move(nfa, states, symbol))
            if target not in ids:
                ids[target] = len(ids)
                queue.append(target)
            row.append(ids[target])
        trans.append(row)
    trap = ids.get(frozenset())
    if trap is None:
        trap = len(trans)
        trans.append([trap] * 128)
    return DFA(trans, accept, 0, trap)


def minimize(dfa):
    groups = defaultdict(set)
    for state in range(len(dfa.trans)):
        groups[dfa.accept.get(state)].add(state)
    blocks = {i: group for i, group in enumerate(groups.values())}
    owner = {state: i for i, block in blocks.items() for state in block}
    reverse = [defaultdict(set) for _ in ASCII]
    for source, row in enumerate(dfa.trans):
        for symbol, target in enumerate(row):
            reverse[symbol][target].add(source)
    queue = deque(blocks)
    while queue:
        splitter_id = queue.popleft()
        splitter = blocks[splitter_id].copy()
        for symbol in range(128):
            touched = defaultdict(set)
            for target in splitter:
                for source in reverse[symbol].get(target, ()):
                    touched[owner[source]].add(source)
            for block_id, inside in touched.items():
                block = blocks[block_id]
                if len(inside) == len(block):
                    continue
                outside = block - inside
                large, small = (inside, outside) if len(inside) >= len(outside) else (outside, inside)
                new_id = len(blocks)
                blocks[block_id], blocks[new_id] = large, small
                for state in small:
                    owner[state] = new_id
                queue.append(new_id)
    start_block = owner[dfa.start]
    order = [start_block]
    ids = {start_block: 0}
    for block_id in order:
        representative = min(blocks[block_id])
        for target in dfa.trans[representative]:
            target_block = owner[target]
            if target_block not in ids:
                ids[target_block] = len(ids)
                order.append(target_block)
    trap_block = owner[dfa.trap]
    if trap_block not in ids:
        ids[trap_block] = len(ids)
        order.append(trap_block)
    trans, accept = [], {}
    for block_id in order:
        representative = min(blocks[block_id])
        trans.append([ids[owner[t]] for t in dfa.trans[representative]])
        if representative in dfa.accept:
            accept[ids[block_id]] = dfa.accept[representative]
    return DFA(trans, accept, 0, ids[trap_block])


KEYWORDS = "function returns uses while if else assert assume invariant length true false not and or".split()
OPERATORS = "== != <= >= < > = + - * /".split()
DELIMITERS = ", ; ( ) [ ] { }".split()


def funny_rules():
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
    digits = "0123456789"
    return [
        ("WS", True, plus(char_class(" \t\r\n"))),
        ("COMMENT", True, cat(literal("//"), star(char_class(set(ASCII) - {"\r", "\n"})))),
        *((word.upper(), False, literal(word)) for word in KEYWORDS),
        ("IDENT", False, cat(char_class(letters), star(char_class(letters + digits)))),
        ("INT", False, alt(char("0"), cat(char_class("123456789"), star(char_class(digits))))),
        ("OP", False, alt(*(literal(op) for op in OPERATORS))),
        ("DELIM", False, alt(*(literal(delim) for delim in DELIMITERS))),
    ]


def build_funny():
    rules = funny_rules()
    nfa = combine(rules)
    dfa = subset_construction(nfa, rules)
    return nfa, dfa, minimize(dfa)


def step(dfa, state, symbol):
    code = ord(symbol)
    return dfa.trans[state][code] if code < 128 else dfa.trap


def run_dfa(dfa, text):
    state = dfa.start
    best = None
    for symbol in text:
        state = step(dfa, state, symbol)
        if state == dfa.trap:
            break
        if state in dfa.accept:
            best = dfa.accept[state][0]
    return best


def save_dfa(dfa, path):
    data = {
        "start": dfa.start, "trap": dfa.trap, "n_states": len(dfa.trans),
        "accept": {
            state: {"token": name, "skip": skip}
            for state, (name, skip) in dfa.accept.items()
        },
        "trans": {f"{state}|{symbol}": row[ord(symbol)]
                  for state, row in enumerate(dfa.trans) for symbol in ASCII},
    }
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dfa.json"))
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()
    nfa, dfa, minimal = build_funny()
    save_dfa(minimal, args.out)
    save_dfa(dfa, args.out.with_name(args.out.stem + "_before.json"))
    print(f"Rules: {len(funny_rules())}; NFA: {len(nfa.trans)}; "
          f"DFA: {len(dfa.trans)}; min-DFA: {len(minimal.trans)}; "
          f"accept: {len(minimal.accept)}; start={minimal.start}; trap={minimal.trap}")
    if args.tests:
        from test_lexer import run_tests
        run_tests(dfa, minimal, args.out.with_name("tests.md"))


if __name__ == "__main__":
    main()
