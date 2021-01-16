import base64
import logging
import re
from pathlib import Path

from texhtml.toc import TOC
from texhtml.util import optarg, arg, args, next_sibling

class CodexCell:
    def __init__(self, type, caption, content):
        self.type = type
        self.caption = caption
        self.content = content

    def to_html(self) -> str:
        if self.type == "input":
            return self._code_block(self.caption, self.content)
        elif self.type == "plain":
            content = self.content.replace("<", "&lt;").replace(">", "&gt;")
            return f"<pre>{content}</pre>"
        elif self.type == "png":
            return f"<img src='data:image/png;base64, {self.content}' />"
        elif self.type == "table":
            return f"<div class='table-wrapper'>{self.content}</div>"
        return ""

    def _code_block(self, caption, lines):
        code = "\n".join(f"<code>{line}</code>" for line in lines)
        code = f"<pre class='code'>{code}</pre>"
        return f"<div class='code-input'><div class='code-caption'>{caption}</div>\n{code}\n</div>"
    # input return

def codex_row(row):
    if len(row) == 2:
        result = [f"<div class='code-double row'>\n<div class='col-md-6'>",
                   row[0].to_html(),
                   "</div>\n<div class='col-md-6'>",
                   row[1].to_html(),
                   "</div></div>",
                ]
    elif len(row) == 1:
        result = ["<div class='code-single'>", row[0].to_html(), "</div>"]
    else:
        raise Exception(f"Codex rows should have 1 or 2 entries, not {len(row)}")
    return "\n".join(result)

def codex_html(caption, nr, label, rows):
    buffer = [f"<div class='code-example'><h4><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>Example {nr}.</a></small><br/> {caption}</h4>"]
    buffer += [codex_row(row) for row in rows]
    buffer += ["</div>"]
    return "\n".join(buffer)

def kwargs(node):
    # TODO: handle braces correctly :(
    result = {}
    argtext = optarg(node)
    # HACK to parse braces around caption
    if m:=re.search(r"(.*),?caption=\{([^}]+)\}(.*)", argtext):
        result['caption'] = m.group(2)
        argtext = f"{m.group(1)}{m.group(3)}"
    for arg in argtext.split(","):
        if arg.strip():
            try:
                k, v = arg.split("=")
                result[k.strip()] = v.strip()
            except:
                logging.exception(f"Cannot parse {arg} in {argtext}")
                raise
    return result

class UnknownNode(Exception):
    pass

class Parser:
    def __init__(self, base: Path, chapter: int,  toc: TOC):
        self._base = base
        self._toc = toc
        self._chapter = chapter
        self._in_verb = False # Is the preceding command a \verb?
        self.buffer = []

    def _o(self, text):
        self.buffer.append(text)

    def parse(self, node):
        if hasattr(self, node.name):
            result = getattr(self, node.name)(node)
            if result:
                self._o(result)
        else:
            raise UnknownNode(node.name)

    def get_html(self):
        return "\n".join(self.buffer)

    def text(self, node):
        if not node.text:
            return
        text = "".join(node.text)
        if self._in_verb:
            vchr = text[0]
            if vchr not in "+|":
                raise ValueError(f"Unexpected verbatim input: {text}")
            to = text.find(vchr, 1)
            if to == -1:
                raise ValueError(f"Unexpected verbatim input: {text}")
            self._o(f"<span class='verbatim'>{text[1:to]}</span>")
            self._in_verb = False
            text = text[(to+1):]
        self._o(text.replace("\n\n", "</p>\n\n<p>").replace("\\\\", "<br/>"))

    # Structure
    def subsection(self, node):
        self._thesubsection += 1
        nr = f"{self._chapter}.{self._thesection}.{self._thesubsection}"
        label = nr.replace(".", "_")
        return f"<h3><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>{nr}</a></small> {args(node)[0]}</h3>"

    def paragraph(self, node):
        return f"<b>{args(node)[0]}</b>"

    def section(self, node):
        self._thesection += 1
        self._thesubsection = 0
        next = next_sibling(node)
        if next.name == "label":
            label = arg(next)
            nr = self._toc.labels[label]
        else:
            nr = f"{self._chapter}.{self._thesection}"
            label = nr.replace(".", "_")
        return f"<h2><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>{nr}</a></small> {arg(node)}</h2>"


    def chapter(self, node):
        self._thesection = 0
        self._thesubsection = 0
        next = next_sibling(node)
        if next.name == "label":
            label = arg(next)
            nr = self._toc.labels[label]
            return f"<h1><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>Chapter {nr}.</a></small><br/> {arg(node)}</h1>"
        else:
            raise Exception("!")

    # Markup

    def emph(self, node):
        return f"<em>{arg(node)}</em>"

    def textbf(self, node):
        return f"<b>{arg(node)}</b>"

    def ldots(self, node):
        return "..."

    def verb(self, node):
        # This is not parsed correctly by texsoup, so workaround
        self._in_verb = True
        return ""

    def newpage(self, node):
        return

    def ttt(self, node):
        return f"<code>{arg(node)}</code>"
    texttt = ttt

    def verbatim(self, node):
        return f"<pre>{node.text[0]}</pre>"

    def vspace(self, node):
        pass
    noindent = vspace

    # Concepts
    def _concept(self, name: str):
        return f"<span class='concept'>{name}</span> "

    def concept(self, node):
        return self._concept(args(node)[0])
    pkg = fn = concept

    def _fixed_concept(self, node):
        return self._concept(node.name)
    pandas = tidyverse = sklearn = numpy = _fixed_concept

    def abstract(self, node):
        caption = arg(node)
        text = node.text[1]
        print(node.text)
        return f"<div class='abstract'><span class='caption'>{caption}</span> {text}</div>"

    def objectives(self, node):
        items = '\n'.join(f"<li>{item.text[0]}" for item in node)
        return f"<div class='objectives'><div class='caption'>Chapter objectives:</div><ul>{items}</ul></div>"

    def feature(self, node):
        parser = Parser(self._base, self._chapter, self._toc)
        for child in node.all:
            parser.parse(child)
        inner = "\n".join(x for x in parser.buffer if x)
        return f"<div class='feature'>{inner}</div>"

    def keywords(self, node):
        return f"<div class='keywords'><span class='caption'>Keywords:</span> {node.text[0]}</div>"

    # References
    def _ref(self, label, ref):
        if ref not in self._toc.labels:
            logging.warning(f"unknown reference: {ref}")
            file, nr = "", "??"
        else:
            nr = self._toc.labels[ref]
            chap = int(nr.split(".")[0])
            file = "" if chap == self._chapter else f"chapter{chap:02d}.html"
        return f"<a href='{file}#{ref}'>{label} {nr}</a>"

    def refex(self, node):
        return self._ref("Example", f"ex:{arg(node)}")

    def refchap(self, node):
        return self._ref("Chapter", f"chap:{arg(node)}")

    def refsec(self, node):
        return self._ref("Section", f"sec:{arg(node)}")

    def reftab(self, node):
        return self._ref("Table", f"tab:{arg(node)}")
    def reffig(self, node):
        return self._ref("Figure", f"tab:{arg(node)}")


    # Code snippets
    def _code_input(self, fn, caption):
        snippet_file = self._base / "snippets" / f"{fn}"
        code = snippet_file.open().read()
        lines = [x.replace("<", "&lt;").replace(">", "&gt;")
                 for x in code.split("\n")]
        return CodexCell("input", caption, lines)

    def _code_output(self, fn, caption, format):
        suffix = dict(plain=".out", png=".png", table=".table.html")[format]
        out_file = self._base / "snippets" / f"{fn}{suffix}"
        if format == "png":
            png = out_file.open("rb").read()
            result = base64.b64encode(png).decode('ascii')
        else:
            result = out_file.open().read()
        return CodexCell(format, caption, result)

    def pyrex(self, node):
        fn = arg(node)
        label = f"ex:{Path(fn).name}"
        opts = kwargs(node)
        caption = opts.get('caption')
        nr = self._toc.labels[label]
        logging.debug(f"Processing pyrex {nr}: {caption}")
        rows = []
        what_input = opts.get('input', 'both')
        if what_input != 'none':
            rows.append([])
            if what_input in {'py', 'both'}:
                rows[-1] += [self._code_input(f"{fn}.py", "Python code")]
            if what_input in {'r', 'both'}:
                rows[-1] += [self._code_input(f"{fn}.r", "R code")]

        what_output = opts.get('output', 'both')
        format = opts.get('format', 'plain')
        if what_output != 'none':
            rows.append([])
            if what_output in {'py', 'both'}:
                rows[-1] += [self._code_output(f"{fn}.py", f"{'Python' if what_output == 'both' else ''} output", format)]
            if what_output in {'r', 'both'}:
                rows[-1] += [self._code_output(f"{fn}.r", f"{'R' if what_output == 'both' else ''} output", format)]
        return codex_html(caption, nr, label, rows)

    def ccsexample(self, node):
        rows = []
        caption = arg(node.caption)
        label = arg(node.label)
        nr = self._toc.labels[label]
        logging.debug(f"Processing ccsexample {nr}:{caption}")
        for child in node:
            if child.name == "doublecodex":
                fn = arg(child)
                py = self._code_input(f"{fn}.py", "Python code")
                r = self._code_input(f"{fn}.r", "R code")
                rows.append([py, r])
            if child.name == "codex":
                fn = arg(child)
                if fn.endswith(".out"):
                    # output, sorry for the hack
                    fn = fn[:-len(".out")]
                    rows.append([self._code_output(fn, "", "plain")])
                else:
                    raise Exception("!")
            if child.name == "codexoutputtable":
                fn = arg(child)
                rows.append([self._code_output(fn, "", "table")])
            if child.name == "codexoutputpng":
                fn = arg(child)
                rows.append([self._code_output(fn, "", "png")])
            if child.name == "doubleoutput":
                py = self._code_output(f"{fn}.py", "Python code", "plain")
                r = self._code_output(f"{fn}.r", "R code", "plain")
                rows.append([py, r])

        return codex_html(caption, nr, label, rows)

    def doublecodex(self, node):
        fn = arg(node)
        py = self._code_input(f"{fn}.py", "Python code")
        r = self._code_input(f"{fn}.r", "R code")
        return f"<div class='code-example'>{codex_row([py, r])}</div>"

