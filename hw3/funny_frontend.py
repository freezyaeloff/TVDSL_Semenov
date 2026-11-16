"""Typed syntax for Funny, extending the lexer/DFA and parser from HW2."""

from hw2.funny_parser import Parser as BaseParser, ParseError, Token, load_dfa, node, step


def tokenize(source):
    """Use the HW2 DFA, with ':' and the keyword 'let' added for HW3."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    dfa = load_dfa()
    tokens = []
    pos, line, column = 0, 1, 1
    while pos < len(source):
        if source[pos] == ":":
            tokens.append(Token(":", ":", line, column))
            pos, column = pos + 1, column + 1
            continue
        state, index, best = dfa.start, pos, None
        while index < len(source):
            state = step(dfa, state, source[index])
            if state == dfa.trap:
                break
            index += 1
            if state in dfa.accept:
                kind, skip = dfa.accept[state]
                best = index, kind, skip
        if best is None:
            raise ParseError(f"{line}:{column}: неизвестный символ {source[pos]!r}")
        end, kind, skip = best
        text = source[pos:end]
        if not skip:
            if kind == "IDENT" and text in ("requires", "ensures", "let"):
                kind = text.upper()
            if kind in ("OP", "DELIM"):
                kind = text
            tokens.append(Token(kind, text, line, column))
        lines = text.split("\n")
        if len(lines) > 1:
            line, column = line + len(lines) - 1, len(lines[-1]) + 1
        else:
            column += len(text)
        pos = end
    tokens.append(Token("EOF", "", line, column))
    return tokens


class Parser(BaseParser):
    
    def type_annotation(self):
        start = self.current
        name = self.expect("IDENT")
        result = node("TypeName", start, name=name.text)
        while self.match("["):
            self.expect("]")
            result = node("ArrayType", start, element=result)
        return result

    def typed_names(self):
        self.expect("(")
        declarations = []
        if not self.at(")"):
            while True:
                name = self.expect("IDENT")
                annotation = self.type_annotation() if self.match(":") else None
                declarations.append(node("Declaration", name, name=name.text,
                                         annotation=annotation))
                if not self.match(","):
                    break
        self.expect(")")
        return declarations

    def function(self):
        start = self.expect("FUNCTION")
        name = self.expect("IDENT")
        params = self.typed_names()
        self.expect("RETURNS")
        returns = self.typed_names()
        uses = self.typed_names() if self.match("USES") else []
        requires, ensures = [], []
        while self.at("REQUIRES", "ENSURES"):
            keyword = self.take()
            expression = None if self.at(";") else self.expression()
            self.expect(";")
            (requires if keyword.kind == "REQUIRES" else ensures).append(expression)
        return node("Function", start, name=name.text,
                    name_position={"line": name.line, "column": name.column},
                    params=[d["name"] for d in params],
                    returns=[d["name"] for d in returns],
                    uses=[d["name"] for d in uses],
                    declarations={"params": params, "returns": returns, "uses": uses},
                    requires=requires, ensures=ensures, body=self.block())

    def statement(self):
        if self.at("LET"):
            self.take()
            name = self.expect("IDENT")
            annotation = self.type_annotation() if self.match(":") else None
            value = self.expression() if self.match("=") else None
            self.expect(";")
            return node("VarDecl", name, name=name.text, annotation=annotation, value=value)
        return super().statement()


def parse(source):
    parser = Parser(tokenize(source))
    tree = parser.program()
    return tree, parser.errors
