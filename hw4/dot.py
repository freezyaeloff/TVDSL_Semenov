import json


PALETTE = ("#bfdbfe", "#bbf7d0", "#fde68a", "#fecdd3", "#ddd6fe", "#fed7aa")


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def format_dot(report, kind):
    cfg = kind == "cfg"
    graph = "digraph" if cfg else "graph"
    lines = [f"{graph} {kind} {{", '  node [fontname="monospace"];']

    for phase, title in (("before", "До оптимизаций"), ("after", "После оптимизаций")):
        for number, (function, info) in enumerate(report[phase]["analysis"].items()):
            group = f"{phase}_{number}"
            label = f"{function} — {title}"
            if cfg:
                label += f"\nБлоков {info['metrics']['blocks']}"
            lines.append(f"  subgraph cluster_{group} {{")
            lines.append(f"    label={quote(label)};")
            if cfg:
                for block, targets in info["cfg"].items():
                    lines.append(f'    {group}_{block} [shape=box, label="{block}"];')
                    for index, target in enumerate(targets):
                        edge = ""
                        if len(targets) == 2:
                            edge = (' [label="true"]', ' [label="false"]')[index]
                        lines.append(f"    {group}_{block} -> {group}_{target}{edge};")
            else:
                for name, neighbors in info["conflicts"].items():
                    color = info["colors"][name]
                    fill = PALETTE[color % len(PALETTE)]
                    label = quote(f"{name} [{color}]")
                    lines.append(f'    {group}_{name} [style=filled, fillcolor="{fill}", label={label}];')
                    for neighbor in neighbors:
                        if name < neighbor:
                            lines.append(f"    {group}_{name} -- {group}_{neighbor};")
                if not info["conflicts"]:
                    lines.append(f'    {group}_empty [shape=plaintext, label="Нет временных"];')
            lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"
