import logging
import shutil
import sys
import re
from collections import namedtuple
from io import StringIO
from itertools import count
from pathlib import Path
from typing import List

from PIL.Image import Image
from TexSoup.utils import Token
from markupsafe import escape
import TexSoup
from TexSoup.data import BraceGroup, BracketGroup, TexExpr, TexEnv, TexCmd

from tools.texhtml.toc import TOC
from tools.texhtml.util import args, arg

IGNORE = {
    "centering",
    "index",
    "label",
    "newpage",
    "noindent"
}
SIMPLE_ENVS = {
    "[tex]": None,
    "feature": "div class='feature'",
    "item": "li",
    #"figure": "div class='figure'",
}
SIMPLE_COMMANDS = {
    "small": None,
    "textit": "em",
    "texttt": "code",
    "ttt": "code",
    "textbf": "b",
    "emph": "i",
    "paragraph": "b",
    "concept": "i",

}
SIMPLE_NODES = {
    "textbar": "|",
    "textbackslash": "\\",
    "tidyverse": "<code>tidyverse</code>",
    "pandas": "<code>pandas</code>",
}
SUBS = {
    "<": "&lt;",
    "\\{": "{",
    "\\}": "}",
    "\\\\": "<br/>",
    "~": "&nbsp;",
    "\\&": "&amp;",
    '``': '&ldquo;',
    "''": '&rdquo;',
    "\\#": '#',
    "\\%": "%",
    "\\_": "_",
    "\\$": "$",
    "\\^": "^",
}
ACCENTS = {
    "\\'": 'acute'
}


class Parser:
    def __init__(self, *, base:Path, out_folder:Path,
                 chapter:int, toc: TOC, bibliography: dict, verbs:List[str]=None, sink=sys.stdout):
        self._sink = sink
        self._toc = toc
        self._bibliography = bibliography
        self._thechapter = chapter
        self._thesection = 0
        self._thesubsection = 0
        self._verbs = [] if verbs is None else verbs
        self._depth = -1
        self._n_notes = 0
        self._in_p = False  # Is the outer mode in a <p> tag?
        self._unknown_nodes = set()
        self._base = base
        self._out_folder = out_folder
        self._img_folder = self._out_folder / "img"
        self._img_folder.mkdir(parents=True, exist_ok=True)


    def emit(self, text: str):
        self._sink.write(text)

    def parse(self, nodes):
        self._depth += 1
        while nodes:
            node = nodes.pop(0)
            self.parse_node(node, nodes)
        self._depth -= 1

    def parse_str(self, nodes):
        old, self._sink = self._sink, StringIO()
        self.parse(nodes)
        result, self._sink = self._sink.getvalue(), old
        return result


    def parse_node(self, node, nodes):
        assert isinstance(node, TexExpr), f"Node is not a TexExpr but a {type(node)}: {repr(node)}"
        if hasattr(self, node.name):
            getattr(self, node.name)(node, nodes)
        elif node.name == "$":
            self.dollar(node)
        elif node.name in SIMPLE_ENVS:
            self.simple_env(node)
        elif node.name in SIMPLE_COMMANDS:
            self.simple_cmd(node)
        elif node.name in SIMPLE_NODES:
            self.simple_node(node)
        elif node.name in IGNORE:
            pass
        else:
            self._unknown_nodes.add(node.name)
            logging.warning(f"Unknown node: {node.name} [{type(node)}: {repr(node)[:20]}...]")

    def simple_node(self, node):
        html = SIMPLE_NODES[node.name]
        self.emit(html)

    def simple_env(self, node):
        tag = SIMPLE_ENVS[node.name]
        if tag:
            self.emit(f"<{tag}>")
        self.parse(node._contents)
        if tag:
            end_tag = tag.split(" ")[0]
            self.emit(f"</{end_tag}>")

    def simple_cmd(self, node):
        self._open_p()
        args = [a for a in node.args if isinstance(a, BraceGroup)]
        assert len(args) == 1, f"#arguments != 1: [{node.name}] {repr(args)} : {repr(node)}"
        assert isinstance(node, TexCmd)
        tag = SIMPLE_COMMANDS[node.name]
        if tag:
            self.emit(f"<{tag}>")
        self.parse(args[0]._contents)
        if tag:
            end_tag = tag.split(" ")[0]
            self.emit(f"</{end_tag}>")

    def text(self, node, nodes):
        text = [str(node)]
        while nodes and nodes[0].name == "text":
            text.append(str(nodes.pop(0)))
        text = "".join(text)
        for k, v in SUBS.items():
            text = text.replace(k, v)
        text = re.sub("%.*", "", text)
        if self._depth == 0:
            for par in re.split(r"(\n\s*\n)", text):
                if re.match(r"(\n\s*\n)", par):
                    self._close_p()
                elif par.strip():
                    self._open_p()
                    self.emit(f"\n{par}\n")
        elif text.strip():
            self.emit(f" {text.strip()} ")

    def _close_p(self):
        if self._depth == 0 and self._in_p:
            self.emit("\n</p>\n")
            self._in_p = False

    def _open_p(self):
        if self._depth == 0 and not self._in_p:
            self.emit("\n<p>\n")
            self._in_p = True

    ###### MATH ######

    def dollar(self, node):
        expr = str(node).strip("$")
        self.emit(f"\\({expr}\\)")

    ###### MARKUP #####

    def verbatim(self, node, _nodes):
        assert len(node._contents) == 1
        text = escape(str(node._contents[0]))

        self.emit(f"<pre>{text}</pre>")

    def verbplaceholder(self, node, _nodes):
        self._open_p()
        n = int(arg(node))
        self.emit(f"<code>{self._verbs[n]}</code>")


    def accent(self, node, nodes):
        assert len(nodes) > 0
        accent = ACCENTS[str(node)]
        next = nodes.pop(0)
        if getattr(next, "name", None) == "BraceGroup":
            text = "".join(next.text)
        elif isinstance(next, TexSoup.utils.Token):
            text = str(next)
        else:
            raise TypeError(next)
        self.emit(f"&{text[0]}{accent};{text[1:]}")

    def url(self, node, nodes):
        href, = _args(node)
        text = re.sub("https?://", "", href)
        self.emit(f"<a href='{href}'>{text}</a>")

    def footnote(self, node, nodes):
        inner = self.parse_str(node.args[0]._contents)
        # Footnote cannot contain math, so un-jax it:
        #TODO: deal with expressions within footnotes?
        inner = inner.replace("\\(", " <em>").replace("\\)", "</em> ")
        self._n_notes += 1
        self.emit(f'<a tabindex="0" class="note" data-bs-trigger="focus" data-bs-toggle="popover" title="Note {self._n_notes}" data-bs-content="{inner}">[{self._n_notes}]</a>')

    ######### STRUCTURE #########
    def _get_label(self, nodes):
        """Get the label from the next non-text node"""
        for i in count():
            if nodes[i].name == "text":
                continue
            elif nodes[i].name == "label":
                return str(nodes[i].args[0].string)
            else:
                return

    def chapter(self, node, nodes):
        assert len(node.args) == 1
        label = self._get_label(nodes)
        nr = self._toc.labels[label]
        self.emit(f"\n<h1><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>Chapter {nr}.</a></small><br/>\n")
        self.parse(node.args[0]._contents)
        self.emit("\n</h1>\n\n")

    def section(self, node, nodes):
        self._close_p()
        self._thesection += 1
        self._thesubsection = 0
        logging.info(f"Processig section {self._thesection}: {node.args[0]}")
        nr = f"{self._thechapter}.{self._thesection}"
        label = nr.replace(".", "_")
        self.emit(f"\n<h2><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>{nr}</a></small>\n")
        self.parse(node.args[0]._contents)
        self.emit("\n</h2>\n\n")

    def subsection(self, node, nodes):
        self._close_p()
        self._thesubsection += 1
        nr = f"{self._thechapter}.{self._thesection}.{self._thesubsection}"
        logging.info(f"... Processig subsection {nr}: {node.args[0]}")
        label = nr.replace(".", "_")
        self.emit(f"\n<h3><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>{nr}</a></small>\n")
        self.parse(node.args[0]._contents)
        self.emit("\n</h3>\n\n")

    def abstract(self, node, _nodes):
        self._close_p()
        assert len(node.args) == 1
        self.emit("\n<div class='abstract'>\n  <span class='caption'>\n")
        self.parse(node.args[0]._contents)
        self.emit("\n  </span>")
        self.parse(node._contents)
        self.emit("\n</div>")

    def keywords(self, node, _nodes):
        self._close_p()
        assert len(node.args) == 1
        self.emit("\n\n<div class='keywords'>\n  <span class='caption'>Keywords:</span>\n")
        self.parse(node.args[0]._contents)
        self.emit("\n</div>")

    def objectives(self, node, _nodes):
        self._close_p()
        self.emit("\n<div class='objectives'>\n  <div class='caption'>Chapter objectives:</div>\n  <ul>")
        self.parse(node._contents)
        self.emit("\n  </ul>\n</div>")

    ### FIGURES / TABLES ###
    def figure(self, node, _nodes):
        self.emit("<div class='figure'>")
        # pull caption and label to start
        nodes = list(node._contents)
        nodes = [_pop_named(nodes, "caption"), _pop(nodes, "label")] + nodes
        self.parse(nodes)
        self.emit("</div>")

    def includegraphics(self, node, _nodes):
        img = Path(_args(node)[0])
        if img.suffix in (".pdf", ".eps"):
            img = img.with_suffix(".png")
        self.emit(self._img_html(img))

    def _img_html(self, img: Path):
        outf = self._img_folder / img.name
        shutil.copy(self._base / img, outf)
        thumb = thumbnail(outf)
        return f"<a href='img/{img.name}' title='Click to open full-size image'>\n  <img src='img/{thumb.name}' />\n</a>"

    def caption(self, node, nodes):
        ref = self._get_label(nodes)
        nr = self._toc.labels[ref]
        label = {"ex": "Example",
                 "fig": "Figure"}[ref.split(":")[0]]
        print("!!!", ref, nr)
        self.emit(f"<h4><small class='text-muted'><a class='anchor' href='#{ref}' name='{ref}'>{label} {nr}.</a></small><br/>")
        self.parse(node.args[0]._contents)
        self.emit("</h4>")


    ##### CODE EXAMPLES #####
    def _read_snippet(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}"
        code = snippet_file.open().read()
        lines = [x.replace("<", "&lt;").replace(">", "&gt;")
                 for x in code.split("\n")]
        return lines

    def _code_input(self, caption, lines):
        self.emit(f"<div class='code-input'>\n  <div class='code-caption'>{caption}</div>\n  <pre class='code'>")
        for i, line in enumerate(lines):
            if i:
                self.emit("\n")
            if line is None:
                self.emit("&nbsp;")
            else:
                self.emit(f"<code>{line}</code>")
        self.emit("  </pre>\n</div>")

    def _doublecodex(self, fn):
        self._close_p()
        self.emit("<div class='code-row-double'>")
        snippets = [self._read_snippet(f"{fn}.{ext}") for ext in ["py", "r"]]
        add_blank_lines(*snippets)
        self._code_input("Python code", snippets[0])
        self._code_input("R code", snippets[1])
        self.emit("</div>")


    def doublecodex(self, node, nodes):
        self._doublecodex(_arg(node))

    def codex(self, node, nodes):
        #\codex[caption = Output]{chapter02 / tweetsb.r.out}
        fn = _arg(node)
        snippet_file = self._base / "snippets" / f"{fn}"
        content = snippet_file.open().read()
        kwargs = extract_kwargs(_optarg(node))
        content = content.replace("<", "&lt;").replace(">", "&gt;")
        self.emit("<div class='code-single'>")
        self.emit(f"<pre class='output'>{content}</pre>")
        self.emit("</div>")

    def codexoutputtable(self, node, nodes):
        self._codexoutputtable(_arg(node))

    def _codexoutputtable(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.table.html"
        content = snippet_file.open().read()
        self.emit(f"<div class='table-wrapper'>{content}</div>")

    def codexoutputpng(self, node, nodes):
        self._codexoutputpng(_arg(node))
    def _codexoutputpng(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.png"
        self.emit(self._img_html(snippet_file))


    def tcbraster(self, node, nodes):
        self._close_p()
        self.emit("<div class='code-row-double'>")
        codices = [n for n in node._contents if getattr(n, "name", None) == "codex"]
        snippets = [self._read_snippet(_arg(n)) for n in codices]
        add_blank_lines(*snippets)
        captions = [extract_kwargs(_optarg(n))['caption'] for n in codices]
        assert len(codices) == 2
        self._code_input(captions[0], snippets[0])
        self._code_input(captions[1], snippets[1])
        #self.codex(codices[0])
        self.emit("</div>")

    def ccsexample(self, node, nodes):
        self._close_p()
        self.emit(f"<div class='code-example'>")
        nodes = list(node._contents)
        nodes = [_pop_named(nodes, "caption"), _pop_named(nodes, "label")] + nodes
        self.parse(nodes)
        self.emit("</div>")

    def pyrex(self, node, nodes):
        self._close_p()
        self.emit(f"<div class='code-example'>")
        fn = _arg(node)
        kwargs = extract_kwargs(_optarg(node))
        ref = f"ex:{Path(fn).name}"
        nr = self._toc.labels[ref]
        self.emit(f"<h4><small class='text-muted'><a class='anchor' href='#{ref}' name='{ref}'>Example {nr}.</a></small><br/>{kwargs['caption']}</h4>")

        #\pyrex[caption=Barplot of tweets over time,input=both,output=r,format=png]{chapter02/funtime}
        if kwargs.get('input', 'both') == 'both':
            self._doublecodex(fn)
        else:
            raise Exception("!")
        output = kwargs.get('output', 'both')
        format = kwargs.get('format', 'plain')
        if output in ('r', 'py'):
            fn = f"{fn}.{output}"
            if format == "png":
                self._codexoutputpng(fn)
            elif format == "table":
                self._codexoutputtable(fn)
            else:
                raise Exception("!")
        else:
            self.emit("<div class='code-row-double'>")
            for output in "py", "r":

            self.emit("</div>")
        self.emit("</div>")

    ##### REFERENCES #####
    def _ref(self, label, ref):
        if ref not in self._toc.labels:
            logging.warning(f"unknown reference: {ref}")
            file, nr = "", "??"
        else:
            nr = self._toc.labels[ref]
            chap = int(nr.split(".")[0])
            if ref.startswith("sec:") or ref.startswith("chap:"):
                ref = nr.replace(".", "_")
            file = "" if chap == self._thechapter else f"chapter{chap:02d}.html"
        if label:
            label = f"{label} "
        self.emit(f"<a href='{file}#{ref}'>{label}{nr}</a>")

    def refchap(self, node, _nodes):
        self._ref("Chapter", f"chap:{_args(node)[0]}")

    def refsec(self, node, _nodes):
        self._ref("Section", f"sec:{_args(node)[0]}")

    def reffig(self, node, _nodes):
        self._ref("Figure", f"fig:{_args(node)[0]}")

    def ref(self, node, _nodes):
        self._ref("", f"{_args(node)[0]}")

    #### CITATIONS ####
    def citep(self, node, nodes):
        self._open_p()
        print(type(node.args))
        opt = _optargs(node)
        if len(opt) == 1:
            pre, post = "", opt[0] + " "
        elif len(opt) == 2:
            pre, post = opt[0] + " ", opt[1] + " "
        else:
            pre, post = "", ""
        self.emit(pre)
        self.citet(node, nodes, add_parentheses=False)
        self.emit(post)

    def citet(self, node, nodes, add_parentheses=True):
        self._open_p()
        refs = []
        arg, = _args(node)
        for item in arg.split(","):
            short, entries = self._bibliography[item.strip()]
            if add_parentheses:
                short = re.sub(r", (\d\d\d\d)", " (\\1)", short)
            entry = " ".join(entries)
            html = f'<span class="cite" title="{entry}">{short}</span>'
            refs.append(html)
        self.emit('; '.join(refs))
    def citealp(self, node):
        self.citet(node, add_parentheses=False)
    cite = citet


def _optargs(node):
    return [str(x.string) for x in node.args if isinstance(x, BracketGroup)]


def _optarg(node):
    args = _optargs(node)
    assert len(args) == 1, f"#Optional Arguments != 1: {args} [{node}]"
    return args[0]


def _args(node):
    return [str(x.string) for x in node.args if isinstance(x, BraceGroup)]


def _arg(node):
    args = _args(node)
    assert len(args) == 1, f"#Arguments != 1: {args} [{node}]"
    return args[0]


def extract_kwargs(argtext):
    # TODO: handle braces correctly :(
    result = {}
    # HACK remove index/emph tags from caption since they mess up processing
    argtext = re.sub(r"\\index\{([^}]+)}", "", argtext)
    argtext = re.sub(r"\\(emph|texttt)\{([^}]+)}", "\\2", argtext)
    if "\\refex" in argtext:
        m = re.match(r"(.*)\\refex\{([^}]+)}(.*)", argtext)
        pre, ex, post = m.groups()
        ex = self._ref("Example", f"ex:{ex}")
        argtext = "".join([pre, ex, post])

    argtext = re.sub(r"\\refex\{([^}]+)}", "", argtext)
    # HACK to parse braces around caption
    if m := re.search(r"(.*),?caption=\{([^}]+)\}(.*)", argtext):
        result['caption'] = m.group(2)
        argtext = f"{m.group(1)}{m.group(3)}"
    for arg in argtext.split(","):
        if arg.strip():
            try:
                k, v = arg.split("=")
                result[k.strip()] = v.strip()
            except:
                logging.exception(f"Cannot parse {repr(arg)} in {argtext}")
                raise
    return result

def add_blank_lines(lines1, lines2):
    n = len(lines1) - len(lines2)
    if n > 0:
        lines2 += [None] * n
    elif n < 0:
        lines1 += [None] * -n


def thumbnail(img: Path, size=640) -> Path:
    assert img.suffix == ".png"
    outf = img.parent / f"{img.stem}_thumb{img.suffix}"
    if not outf.exists():
        im = Image.open(img)
        im.thumbnail((size, size))
        im.save(outf)
    return outf

def _pop_named(nodes, name):
    return nodes.pop([node.name for node in nodes].index(name))


def preprocess(tex: str):
    verbs = []
    buffer = []
    for x in re.split(r"(\\verb\|[^|]+\||\\verb\+[^+]+\+)", tex):
        if m := (re.match(r"\\verb\|([^|]+)\|", x) or re.match(r"\\verb\+([^+]+)\+", x)):
            buffer.append(f"\\verbplaceholder{{{len(verbs)}}}")
            verbs.append(m.group(1))
        elif m := re.match(r"\\SaveVerb\{(\w+)\}\|([^|]+)\|", x):
            print("????", m.groups())
        else:
            buffer.append(x)
    tex = "".join(buffer)
    tex = tex.replace("\\ ", " ").replace("\\,", "")
    return tex, verbs


if __name__ == '__main__':
    tex = " ".join(sys.argv[1:])
    #tex, verbs = preprocess(tex)
    nodes = TexSoup.TexSoup(tex).expr._contents
    #p = Parser(chapter=1, sink=StringIO(), verbs=verbs)
    #p.parse([root])
    #print(p.sink.getvalue())
