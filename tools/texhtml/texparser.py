import logging
import shutil
import sys
import re
from collections import namedtuple
from io import StringIO
from itertools import count
from pathlib import Path
from typing import List

from PIL import Image
from TexSoup.utils import Token
from markupsafe import escape
import TexSoup
from TexSoup.data import BraceGroup, BracketGroup, TexExpr, TexEnv, TexCmd

from tools.texhtml.toc import TOC

IGNORE = {
    "centering",
    "index",
    "label",
    "newpage",
    "noindent",
    "center",
    "toprule",
    "bottomrule",
}
SIMPLE_ENVS = {
    "[tex]": None,
    "feature": "div class='feature'",
    "item": "li",
    "table": "div class='figure'"
}
SIMPLE_COMMANDS = {
    "textit": "em",
    "texttt": "code",
    "ttt": "code",
    "textbf": "b",
    "emph": "i",
    "paragraph": "b",
    "concept": "code",
    "fn": "code",

}
SIMPLE_NODES = {
    "textbar": "|",
    "textbackslash": "\\",
    "textless": "&lt;",
    "ldots": "&hellip;",
    "lbrack": "[",
    "rbrack": "]",
    "tidyverse": "<code>tidyverse</code>",
    "pandas": "<code>pandas</code>",
}
SUBS = {
    "<": "&lt;",
    "\\{": "{",
    "\\}": "}",
    "~": "&nbsp;",
    "\\&": "&amp;",
    '``': '&ldquo;',
    "''": '&rdquo;',
    '--': '&ndash;',
    "\\#": '#',
    "\\%": "%",
    "\\_": "_",
    "\\$": "$",
    "\\^": "^",
    "\\(": "(",
    "\\)": ")",
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
        self._intable = False


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
            self.simple_node(node, nodes)
        elif node.name in IGNORE:
            pass
        else:
            self._unknown_nodes.add(node.name)
            logging.warning(f"Unknown node: {node.name} [{type(node)}: {repr(node)[:20]}...]")

    ##### GENERIC MARKUP #####

    def simple_node(self, node, nodes):
        html = SIMPLE_NODES[node.name]
        self.emit(html)
        if nodes and nodes[0].name == "text" and nodes[0].string.startswith(" "):
            next = nodes.pop(0)
            text = str(next.string).lstrip(" ")
            self._text(text)


    def simple_env(self, node):
        tag = SIMPLE_ENVS[node.name]
        if tag:
            self.emit(f"<{tag}>")
        self.parse(node._contents)
        if tag:
            end_tag = tag.split(" ")[0]
            self.emit(f"</{end_tag}>")

    def color(self, node, _nodes):
        color = _arg(node)
        self.emit(f"<span class='{color}'>")
        self.parse(node._contents)
        self.emit("</span>")

    def BraceGroup(self, node, _nodes):
        # This should only be called for an 'isolated' bracegroup, e.g. {\color } etc
        self.parse(node._contents)
        #print(node._contents, _nodes and _nodes[0])

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

    def small(self, node, _nodes):
        self._open_p()
        args = [a for a in node.args if isinstance(a, BraceGroup)]
        for arg in args:
            self.parse(arg._contents)

    def text(self, node, nodes):
        if str(node) in ACCENTS:
            return self.accent(node, nodes)
        text = [str(node)]
        while nodes and nodes[0].name == "text" and not str(nodes[0]).startswith("\\"):
            text.append(str(nodes.pop(0)))
        text = "".join(text)
        self._text(text)

    def _text(self, text):
        for k, v in SUBS.items():
            text = text.replace(k, v)
        text = re.sub("%.*", "", text)
        if not self._intable:
            text = text.replace("\\\\", "<br/>")
        if self._depth == 0:
            for i, par in enumerate(re.split(r"(\n\s*\n)", text)):
                if re.match(r"(\n\s*\n)", par):
                    self._close_p()
                elif par.strip():
                    self._open_p()
                    self.emit(f"{par}")
        elif self._intable:
            self._table_text(text)
        elif self._in_p or text.strip():
            self.emit(f"{text}")

    def _close_p(self):
        if self._depth == 0 and self._in_p:
            self.emit("\n</p>\n")
            self._in_p = False

    def _open_p(self):
        if self._intable:
            self._open_cell()
        elif self._depth == 0 and not self._in_p:
            self.emit("\n<p>\n")
            self._in_p = True

    ###### MATH ######

    def dollar(self, node):
        expr = str(node).strip("$")
        if self._intable and expr == "\\cdots":
            self.emit("&hellip;")
        else:
            self.emit(f"\\({expr}\\)")

    ###### MARKUP #####

    def verbatim(self, node, _nodes):
        assert len(node._contents) == 1
        text = escape(str(node._contents[0]))

        self.emit(f"<pre>{text}</pre>")

    def verbplaceholder(self, node, _nodes):
        self._open_p()
        verb = escape(self._verbs[int(_arg(node))])
        self.emit(f"<code>{verb}</code>")


    def accent(self, node, nodes):
        assert len(nodes) > 0
        accent = ACCENTS[str(node)]
        next = nodes.pop(0)
        if getattr(next, "name", None) == "BraceGroup":
            text = "".join(next.string)
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
        self.emit(f"\n<h1>")
        self._caption(label, nr, br=False)
        self.parse(node.args[0]._contents)
        self.emit("\n</h1>\n\n")

    def section(self, node, _nodes):
        self._close_p()
        self._thesection += 1
        self._thesubsection = 0
        nr = f"{self._thechapter}.{self._thesection}"
        logging.info(f"Processing section {nr}: {node.args[0]}")
        label = nr.replace(".", "_")
        self.emit(f"\n<h2>")
        self._caption(label, nr, br=False)
        self.parse(node.args[0]._contents)
        self.emit("\n</h2>\n\n")

    def subsection(self, node, _nodes):
        self._close_p()
        self._thesubsection += 1
        nr = f"{self._thechapter}.{self._thesection}.{self._thesubsection}"
        logging.info(f"... Processig subsection {nr}: {node.args[0]}")
        label = nr.replace(".", "_")
        self.emit(f"\n<h3>")
        self._caption(label, nr, br=False)
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

    def enumerate(self, node, _nodes):
        self._close_p()
        self.emit("\n<ol>")
        self.parse(node._contents)
        self.emit("\n</ol>")

    ### FIGURES / TABLES ###

    def figure(self, node, nodes):
        self.emit("<div class='figure'>")
        # pull caption and label to start
        nodes = list(node._contents)
        nodes = [_pop_named(nodes, "caption"), _pop_named(nodes, "label")] + nodes
        self.parse(nodes)
        self.emit("</div>")

    def includegraphics(self, node, _nodes):
        if self._intable:
            self._open_cell()
        img = Path(_args(node)[0])
        if img.name == "emoji.pdf":
            return self.emit("&#x1F60A;")
        elif img.name == "hangul.pdf":
            return self.emit("&#54620;&#44544;")
        elif img.name == "tango.pdf":
            return self.emit("&#21336;&#35486;")
        if img.suffix in (".pdf", ".eps"):
            img = img.with_suffix(".png")
        html = self._img_html(img)
        self.emit(html)

    def _img_html(self, img: Path):
        outf = self._img_folder / img.name
        shutil.copy(self._base / img, outf)
        im = Image.open(outf)
        if im.size[0] > 640 or im.size[1] > 640:
            thumb = thumbnail(outf)
            return f"<a href='img/{img.name}' title='Click to open full-size image'>\n  <img src='img/{thumb.name}' />\n</a>"
        else:
            return f"<img src='img/{img.name}' />"

    def _wiley_table(self, caption, body, notes):
        ref = self._get_label(caption._contents)
        #self.parse(caption._contents)
        self._float(ref, caption._contents)
        self.parse(body._contents)

    def tabularx(self, node, _nodes):
        size, columns = _args(node)
        self._intable = dict(columns=list(columns), inhead=True, inrow=None, incell=False)
        self.emit("<table class='table'>")
        self.emit("<thead>\n")
        self.parse(node._contents)
        self._close_row()
        self.emit(f"</{'thead' if self._intable['inhead'] else 'tbody'}>\n")
        self.emit("</table>")
        self._intable = None

    def multicolumn(self, node, _nodes):
        self._open_row()
        ncol, _just, content = node.args
        ncol = int(ncol.string)
        self._open_cell(ncol=ncol)
        self.parse(content._contents)
        #self._close_cell()

    def _table_text(self, text):
        for t in re.split(r"(\\\\|&)", text):
            if t == "\\\\":
                self._close_row()
            elif t == "&":
                if not self._intable['incell']:
                    self._open_cell() # empty cell
                self._close_cell()
            elif self._intable['incell'] or t.strip():
                self._open_cell()
                self.emit(t)

    def _close_row(self):
        if self._intable['inrow'] is not None:
            empty_cells = len(self._intable['columns']) - self._intable['inrow']
            self._close_cell()
            if empty_cells > 0:
                self._open_cell(ncol=empty_cells)
                self._close_cell()
            self.emit(f"\n  </tr>\n")
            self._intable['inrow'] = None

    def _open_row(self):
        if self._intable['inrow'] is None:
            self.emit(f"  <tr>\n")
            self._intable['inrow'] = 0
            self._intable['incell'] = False

    def _open_cell(self, ncol=1):
        if not self._intable['incell']:
            self._open_row()
            extra = f' colspan="{ncol}"' if ncol > 1 else ''
            self.emit(f"    <{'th' if self._intable['inhead'] else 'td'}{extra}>\n")
            self._intable['incell'] = True
            self._intable['inrow'] += ncol

    def _close_cell(self):
        if self._intable['incell']:
            self.emit(f"\n    </{'th' if self._intable['inhead'] else 'td'}>\n")
            self._intable['incell'] = False

    def midrule(self, _node, _nodes):
        self._close_row()
        if self._intable['inhead']:
            self.emit(f"</thead><tbody>\n")
            self._intable['inhead'] = False

    def cmidrule(self, _node, nodes):
        # Pop the (lr) argument (if available), and the {3-4} argument
        next = nodes.pop(0)
        if re.match(r"\(\w+\)", str(next)):
            nodes.pop(0)

    def caption(self, node, nodes):
        if len(node.args) == 3:
            # Wiley has weird tables - the caption has arguments {caption}{body}{note}
            return self._wiley_table(*node.args)
        ref = self._get_label(nodes)
        self._float(ref, node.args[0]._contents)

    def _float(self, ref, contents):
        nr = self._toc.labels[ref]
        label = {"ex": "Example",
                 "fig": "Figure",
                 "tab": "Table"}[ref.split(":")[0]]
        self.emit(f"<h4>\n")
        self._caption(ref, f"{label} {nr}")
        self.parse(contents)
        self.emit("</h4>\n")

    def _caption(self, ref, label, br=True, caption=None):
        self.emit(f"  <small class='text-muted'><a class='anchor' href='#{ref}' name='{ref}'>{label}.</a></small>")
        if br:
            self.emit("<br />\n")
        if caption:
            self.emit(caption)

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
        fn = _arg(node)
        snippet_file = self._base / "snippets" / f"{fn}"
        content = snippet_file.open().read()
        kwargs = self.extract_kwargs(_optarg(node))
        content = content.replace("<", "&lt;").replace(">", "&gt;")
        self.emit("<div class='code-single'>")
        self.emit(f"<pre class='output'>{content}</pre>")
        self.emit("</div>")

    def codexoutputtable(self, node, _nodes):
        self._codexoutputtable(_arg(node))

    def _codexoutputtable(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.table.html"
        content = snippet_file.open().read()
        self.emit(f"<div class='table-wrapper'>{content}</div>")

    def codexoutputpng(self, node, _nodes):
        self._codexoutputpng(_arg(node))

    def _codexoutputpng(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.png"
        self.emit(self._img_html(snippet_file))

    def _codexoutputplain(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.out"
        content = snippet_file.open().read()
        content = content.replace("<", "&lt;").replace(">", "&gt;")
        self.emit(f"<pre class='output'>{content}</pre>")

    def _codexoutput(self, fn, format):
        handlers = dict(
            png=self._codexoutputpng,
            table=self._codexoutputtable,
            plain=self._codexoutputplain,
        )
        handlers[format](fn)

    def doubleoutput(self, node, _nodes):
        self._doubleoutput(_arg(node))


    def _doubleoutput(self, fn):
        self.emit("<div class='code-row-double'>")
        for output in "py", "r":
            self._codexoutput(f"{fn}.{output}", "plain")
        self.emit("</div>")

    def tcbraster(self, node, _nodes):
        self._close_p()
        self.emit("<div class='code-row-double'>")
        codices = [n for n in node._contents if getattr(n, "name", None) == "codex"]
        snippets = [self._read_snippet(_arg(n)) for n in codices]
        add_blank_lines(*snippets)
        captions = [self.extract_kwargs(_optarg(n))['caption'] for n in codices]
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
        kwargs = self.extract_kwargs(_optarg(node))
        ref = f"ex:{Path(fn).name}"
        nr = self._toc.labels[ref]
        # Captions from kwargs are not parsed, so manually do required substitutions
        caption = kwargs['caption']
        caption = re.sub(r"\$([^$]+)\$", "<i>\\1</i>", caption)
        self.emit("<h4>")
        self._caption(ref, f"Example {nr}", caption=caption)
        self.emit("</h4>")
        input = kwargs.get('input', 'both')
        if input == 'both':
            self._doublecodex(fn)
        else:
            lines = self._read_snippet(f"{fn}.{input}")
            name = dict(py="Python", r="R")[input]
            self._code_input(f"{name} code", lines)
        output = kwargs.get('output', 'both')
        format = kwargs.get('format', 'plain')
        if output in ('r', 'py'):
            self._codexoutput(f"{fn}.{output}", format)
        elif output == "both":
            self._doubleoutput(fn)
        self.emit("</div>")


    ##### REFERENCES #####
    def _ref(self, label, ref):
        self.emit(self._ref_html(label, ref))

    def _ref_html(self, label, ref):
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
        return f"<a href='{file}#{ref}'>{label}{nr}</a>"

    def refchap(self, node, _nodes):
        self._ref("Chapter", f"chap:{_args(node)[0]}")

    def refsec(self, node, _nodes):
        self._ref("Section", f"sec:{_args(node)[0]}")

    def reffig(self, node, _nodes):
        self._ref("Figure", f"fig:{_args(node)[0]}")

    def refex(self, node, _nodes):
        self._ref("Example", f"ex:{_args(node)[0]}")

    def ref(self, node, _nodes):
        self._ref("", f"{_args(node)[0]}")

    #### CITATIONS ####
    def citep(self, node, nodes):
        self._open_p()
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

    def extract_kwargs(self, argtext):
        # TODO: handle braces correctly :(
        result = {}
        # HACK remove index/emph tags from caption since they mess up processing
        argtext = re.sub(r"\\index\{([^}]+)}", "", argtext)
        argtext = re.sub(r"\\(emph|texttt)\{([^}]+)}", "\\2", argtext)
        if "\\refex" in argtext:
            m = re.match(r"(.*)\\refex\{([^}]+)}(.*)", argtext)
            pre, ex, post = m.groups()
            ex = self._ref_html("Example", f"ex:{ex}")
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
