import html
import logging
import shutil
import subprocess
import sys
import re
import json
import tempfile
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
from black import format_str, FileMode


from tools.texhtml.toc import TOC

BLA = None

IGNORE = {
    "centering",
    "index",
    "label",
    "newpage",
    "noindent",
    "center",
    "toprule",
    "bottomrule",
    "footnotesize",
    "nocite",
    "vspace",
    "hfill",
}
SIMPLE_ENVS = {
    "[tex]": None,
    "feature": "div class='feature'",
    "table": "div class='figure'"
}

SIMPLE_MARKUP = {
    "concept": "`",
    "emph": "*",
    "textbf": "**",
    "texttt": "`",
    "ttt": "`",
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
    "pkg": "code",

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
    "sklearn": "<code>scikit-learn</code>",
    "numpy": "<code>numpy</code>",

}

NBSP = " "

SUBS = {
    '``': '"',
    "''": '"',
    "~": NBSP
}
ACCENTS = {
    "\\'": 'acute',
    '\\"': 'uml',
    '\\`': 'grave',
    '\\=': 'macr',
}


class Parser:
    def __init__(self, *, base:Path, out_folder:Path,
                 chapter:int, toc: TOC, bibliography: dict, verbs:List[str]=None, sink=sys.stdout,
                 notebook_py: str, notebook_r: str
                 ):
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
        self._last_float = None
        self._current_ref = None

        self._current_list = None
        self._current_caption = None
        self._footnotes = []
        self.tags = dict(read_tags(python=notebook_py, r=notebook_r))  # (language: snippet) -> tags
        self.chunk_names = set()

    def emit(self, text: str):
        self._sink.write(text)

    def parse(self, nodes):
        self._depth += 1
        while nodes:
            node = nodes.pop(0)
            self.parse_node(node, nodes)
            if self._current_ref == "xxx":
                return
        self._depth -= 1

    def parse_str(self, nodes, finalize=False):
        old, self._sink = self._sink, StringIO()
        self.parse(nodes)
        if finalize:
            self.finalize()
        result, self._sink = self._sink.getvalue(), old
        return result


    def parse_node(self, node, nodes):
        assert isinstance(node, TexExpr), f"Node is not a TexExpr but a {type(node)}: {repr(node)}"
        if hasattr(self, node.name):
            getattr(self, node.name)(node, nodes)
        elif node.name == "$":
            pass#self.dollar(node)
        elif node.name == "$$":
            pass#self.double_dollar(node)
        elif node.name in SIMPLE_ENVS:
            pass#self.simple_env(node)
        elif node.name in SIMPLE_MARKUP:
            self.simple_markup(node)
        elif node.name in SIMPLE_NODES:
            self.simple_node(node, nodes)
        elif node.name in IGNORE:
            pass
        else:
            self._unknown_nodes.add(node.name)
            logging.warning(f"Unknown node: {node.name} [{type(node)}: {repr(node)[:60]}...]")

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

    def simple_markup(self, node):
        args = [a for a in node.args if isinstance(a, BraceGroup)]
        assert len(args) == 1, f"#arguments != 1: [{node.name}] {repr(args)} : {repr(node)}"
        assert isinstance(node, TexCmd)
        tag = SIMPLE_MARKUP[node.name]
        if tag:
            self.emit(f"{tag}")
        self.parse(args[0]._contents)
        if tag:
            self.emit(f"{tag}")

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
            text = text.replace("\\\\", "\n\n")
        if self._depth == 0:
            for i, par in enumerate(re.split(r"(\n\s*\n)", text)):
                self.emit(f"{par}")
        elif self._intable:
            self._table_text(text)
        elif self._in_p or text.strip():
            self.emit(f"{text}")

    def _close_p(self):
        pass

    def _open_p(self):
        pass

    def finalize(self):
        for i, note in enumerate(self._footnotes):
            self.emit(f"[^{i+1}]: {note}\n\n")

    ###### MATH ######

    def dollar(self, node):
        self._open_p()
        expr = str(node).strip("$")
        if self._intable and expr == "\\cdots":
            self.emit("&hellip;")
        else:
            self.emit(f"\\({expr}\\)")

    def double_dollar(self, node):
        self._close_p()
        mathjax = str(node).strip("$")
        self.emit(f"<p>\\({mathjax}\\)</p>")

    ###### MARKUP #####

    def verbatim(self, node, _nodes):
        assert len(node._contents) == 1
        text = escape(str(node._contents[0])).strip("\n")
        text = str(node._contents[0]).strip("\n")
        self.emit(f"```\n{text}\n```")
    lstlisting = verbatim

    def verbplaceholder(self, node, _nodes):
        self._open_p()
        verb = self._verbs[int(_arg(node))]
        self.emit(f"`{verb}`")


    def accent(self, node, nodes):
        assert len(nodes) > 0
        accent = ACCENTS[str(node)]
        next = nodes.pop(0)
        if getattr(next, "name", None) == "BraceGroup":
            text = "".join(next.string)
        elif isinstance(next, (TexSoup.utils.Token, TexSoup.data.TexText)):
            text = str(next)
        else:
            raise TypeError(f"Expeced token or bracegroup, got {type(next)}: {str(next)}")
        entity = f"&{text[0]}{accent};"
        print(str(node), accent, text, html.unescape(entity))

        self.emit(html.unescape(entity))
        self._text(text[1:])

    def url(self, node, nodes):
        href, = _args(node)
        text = re.sub("https?://", "", href)
        self.emit(f"[{text}]({href})")

    def footnote(self, node, nodes):
        inner = self.parse_str(node.args[0]._contents)
        self._footnotes.append(inner)
        self.emit(f"[^{len(self._footnotes)}]")

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
        self.emit(f"# ")
        self.parse(node.args[0]._contents)
        

    def section(self, node, _nodes):
        logging.info(f"Processing section: {node.args[0]}")
        self.emit(f"\n## ")
        self.parse(node.args[0]._contents)
        label = self._get_label(_nodes)
        if label:
            label = label.replace(":", "-")
            self.emit(f" {{#{label}}}")


    def subsection(self, node, _nodes):
        logging.info(f"... Processig subsection: {node.args[0]}")
        self.emit(f"### ")
        self.parse(node.args[0]._contents)

    def paragraph(self, node, _nodes):
        self.emit("**")
        self.parse(node.args[0]._contents)
        self.emit(".**" )


    def abstract(self, node, _nodes):
        assert len(node.args) == 1
        self.emit("**")
        self.parse(node.args[0]._contents)
        self.emit(".**")
        self.parse(node._contents)

    def keywords(self, node, _nodes):
        assert len(node.args) == 1
        self.emit("**Keywords.** ")
        self.parse(node.args[0]._contents)

    def objectives(self, node, _nodes):
        self.emit("**Objectives:**\n\n")
        self.parse(node._contents)

    def enumerate(self, node, _nodes):
        self._current_list = "enumerate"
        self.parse(node._contents)
    def itemize(self, node, _nodes):
        self._current_list = "itemize"
        self.parse(node._contents)
    description = itemize

    def item(self, node, _nodes):
        self.emit(" - ")
        if node.args:
            args = list(node.args)
            if isinstance(args[0], BracketGroup):
                title = args.pop(0)
                self.emit("**")
                self.parse(title._contents)
                self.emit("**.")
            self.parse(args)
        self.parse(node._contents)
        

    ### FIGURES / TABLES ###

    def minipage(self, node, nodes):
        self.parse(node._contents)

    def figure(self, node, nodes):
        # pull caption and label to start
        nodes = list(node._contents)
        names = [node.name for node in nodes]
        caption = _pop_named(nodes, "caption", strict=False)
        if not caption:
            assert 'feature' in names  # This is not really a figure, just a 'floating feature'
            return self.parse(node._contents)
        label = _pop_named(nodes, "label", strict=False)
        if not label:
            label = _label_from_caption(caption)
        
        self._current_caption = " ".join(caption.args[0].contents)
        self._current_label = " ".join(label.args[0].contents)
        self.parse(nodes)

    def includegraphics(self, node, _nodes):
        if self._intable:
            self._open_cell()

        fn = _arg(node).replace("{", "").replace("}", "")
        img = Path(fn)
        if img.name == "emoji.pdf":
            return self.emit("&#x1F60A;")
        elif img.name == "hangul.pdf":
            return self.emit("&#54620;&#44544;")
        elif img.name == "tango.pdf":
            return self.emit("&#21336;&#35486;")
        if img.suffix in (".pdf", ".eps"):
            img = img.with_suffix(".png")

        outf = self._img_folder / img.name
        shutil.copy(self._base / img, outf)
        self.emit("![")
        self.emit(self._current_caption)
        self.emit(f"](img/{img.name})")
        if self._current_label:
            self.emit(f"{{#{self._current_label.replace(':', '-')}}}")

    def tikzpicture(self, node, _nodes):
        fn = f"{self._last_float.replace(':', '_')}.png"
        tikzfig(self._img_folder / fn, str(node))
        self.emit(f"<img src='img/{fn}' />")
    neuralnetwork=tikzpicture

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
        self._table(node, columns)

    def tabular(self, node, _nodes):
        columns = _arg(node)
        self._table(node, columns)

    def _table(self, node, columns):
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
        for t in re.split(r"(\\\\|&(?!\w+;))", text):
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
        self._last_float = ref
        self.parse(contents)
        self.emit("</h4>\n")

    def _caption(self, ref, label, br=True, caption=None):
        self._current_ref = ref
        self.emit(f"  <small class='text-muted'><a class='anchor' href='#{ref}' name='{ref}'>{label}.</a></small>")
        if br:
            self.emit("<br />\n")
        if caption:
            self.emit(caption)

    def dirtree(self, node, _nodes):
        cur_depth = 0
        for line in _arg(node).split("\n"):
            m = re.match(r"\.(\d+) (.*)\.", line)
            if m:
                text = m.group(2)
                for k, v in SUBS.items():
                    text = text.replace(k, v)
                depth = int(m.group(1))
                if depth == (cur_depth + 1):
                    self.emit("<ul style='list-style-type: \"↪\"'>")
                    cur_depth = depth
                elif depth == (cur_depth - 1):
                    self.emit("</ul>")
                    cur_depth = depth
                self.emit(f"<li>{text}</li>")
        self.emit("</ul>" * cur_depth)

    ### CODE EXAMPLES

    def feature(self, node, _nodes):
        self.emit("\n::: {.callout-note icon=false collapse=true}\n")
        # is there a caption?
        contents = node._contents
        # skip initial empty whitespace
        while contents and isinstance(contents[0], str) and contents[0].strip() == "":
            contents.pop(0)
        if contents and isinstance(contents[0], TexCmd) and contents[0].name == "textbf":
            caption = ''.join(contents.pop(0).contents)
            self.emit(f"## {caption}\n")
            
        self.BLA = list(contents)

        self.parse(contents)
        self.emit("\n:::\n")

    def _read_snippet(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}"
        code = snippet_file.open().read()
        #lines = [x.replace("<", "&lt;").replace(">", "&gt;")
        #         for x in code.split("\n")]
        return code

    def _code_input(self, caption, lines, language=None, snippet=None, execute=None):
        for i in count():
            chunkname = f"{snippet}-{language}{i if i else ''}"
            if chunkname not in self.chunk_names:
                self.chunk_names.add(chunkname)
                break
        if language is None:
            # let's guess the language :D
            if "python" in caption.lower() or "jupyter" in caption.lower():
                language = "python"
            else:
                language = "r"
        tags = self.tags.get((language, snippet), set())
        if execute is None:
            execute = "dontrun" not in tags
        self.emit(f"## {caption}")
        self.emit(f"\n```{{{language} {chunkname}}}\n")
        if not execute:
            self.emit("#| eval: false\n")
        if language == "python" and "!pip" not in lines:
            lines = format_str(lines, mode=FileMode(line_length=80))
        if language == 'python' and "output:png" in tags:
            self.emit("#| results: hide\n")
        self.emit(lines)
        self.emit("\n```\n")

    def _doublecodex(self, fn):
        snippet = fn.split("/")[-1]
        snippets = [self._read_snippet(f"{fn}.{ext}") for ext in ["py", "r"]]
        self.emit("\n::: {.panel-tabset}\n")
        self._code_input("Python code", snippets[0], language="python", snippet=snippet)
        self._code_input("R code", snippets[1], language="r", snippet=snippet)
        self.emit("\n:::\n")

    def doublecodex(self, node, nodes):
        self._doublecodex(_arg(node))

    def codex(self, node, nodes):
        return
        fn = _arg(node)
        snippet_file = self._base / "snippets" / f"{fn}"
        content = snippet_file.open().read()
        kwargs = self.extract_kwargs(_optarg(node))
        content = content.replace("<", "&lt;").replace(">", "&gt;")
        self.emit("<div class='code-single'>")
        self.emit(f"<pre class='output'>{content}</pre>")
        self.emit("</div>")

    def codexoutputtable(self, node, _nodes):
        return
        fn = _arg(node)
        lang = Path(fn).suffix.replace(".", "")
        caption = outputcaption(lang)
        self._codexoutput(_arg(node), "table", caption)

    def _codexoutputtable(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.table.html"
        content = snippet_file.open().read()
        self.emit(f"<div class='table-wrapper'>{content}</div>")

    def codexpng(self, node, _nodes):
        return
        caption, _size, fn = _args(node)
        self._codexoutput(fn, "png", caption)


    def codexoutputpng(self, node, _nodes):
        return

        fn = _arg(node)
        lang = Path(fn).suffix.replace(".", "")
        caption = outputcaption(lang)
        self._codexoutput(_arg(node), "png", caption)

    def _codexoutputpng(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.png"
        self.emit(self._img_html(snippet_file))

    def _codexoutputplain(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.out"
        content = snippet_file.open().read()
        content = content.replace("<", "&lt;").replace(">", "&gt;")
        self.emit(f"<pre class='output'>{content}</pre>")

    def _codexoutputhtml(self, fn):
        snippet_file = self._base / "snippets" / f"{fn}.html"
        content = snippet_file.open().read()
        self.emit(content)


    def _codexoutput(self, fn, format, caption=None):
        self.emit(f"\n<div class='code-output'>")
        if caption:
            self.emit(f"\n    <div class='code-caption'>{caption}</div>\n")
        handlers = dict(
            png=self._codexoutputpng,
            table=self._codexoutputtable,
            plain=self._codexoutputplain,
            html=self._codexoutputhtml,
        )
        handlers[format](fn)
        self.emit("\n</div>")

    def doubleoutput(self, node, _nodes):
        return
        self._doubleoutput(_arg(node), format="plain")


    def _doubleoutput(self, fn, format):
        self.emit("<div class='code-row-double'>")
        for output in "py", "r":
            name = dict(py="Python", r="R")[output]
            self._codexoutput(f"{fn}.{output}", format, f"{name} output")
        self.emit("</div>")

    def tcbraster(self, node, _nodes):
        self.emit("\n::: {.panel-tabset}\n")
        codices = [n for n in node._contents if getattr(n, "name", None) == "codex"]
        if len(codices) == 2:
            snippets = [self._read_snippet(_arg(n)) for n in codices]
            captions = [self.extract_kwargs(_optarg(n))['caption'] for n in codices]
            self._code_input(captions[0], snippets[0], execute=False)
            self._code_input(captions[1], snippets[1], execute=False)
        else:
            boxes = [n for n in node._contents if getattr(n, "name", None) == "tcolorbox"]
            assert len(boxes) == 2
            self.parse(boxes)
        self.emit("\n:::\n")

    def tcolorbox(self, node, _nodes):
        self._close_p()
        kwargs = self.extract_kwargs(_optarg(node))
        self.emit(f"\n<div class='code-output'>")
        if 'title' in kwargs:
            self.emit(f"\n    <div class='code-caption'>{kwargs['title']}</div>\n")
        self.parse(node._contents)
        self.emit("\n</div>")

    def ccsexample(self, node, nodes):
        nodes = list(node._contents)
        caption = _pop_named(nodes, "caption")
        label = _pop_named(nodes, "label", strict=False)
        if not label:
            label = _label_from_caption(caption)
        if not label:
            raise Exception("!")

        caption_text = " ".join(caption.args[0].contents)
        label_text = " ".join(label.args[0].contents).replace("ex:", "exm-")

        self.emit('::: {.callout-note appearance="simple" icon=false}\n')
        self.emit(f"::: {{#{label_text}}}\n{caption_text}\n\n")

        self.parse(nodes)
        self.emit(":::\n")
        self.emit(":::\n")

    def pyrex(self, node, nodes):
        fn = _arg(node)
        kwargs = self.extract_kwargs(_optarg(node))
        ref = f"exm-{Path(fn).name}"

        # Captions from kwargs are not parsed, so manually do required substitutions
        caption = kwargs['caption']
        caption = re.sub("\$([^$]+)\$", "*\\1*", caption)
        parts = []
        for x in re.split(r"(\\['\"`=]\w)", caption):
            if x[:-1] in ACCENTS:
                parts.append(f"&{x[-1]}{ACCENTS[x[:-1]]};")
            else:
                parts.append(x)
        caption = "".join(parts)
        caption = self.parse_str(TexSoup.TexSoup(kwargs['caption']).expr._contents)

        self.emit('\n::: {.callout-note appearance="simple" icon=false}\n')
        self.emit(f'\n::: {{#{ref}}}\n{caption}\n')

        input = kwargs.get('input', 'both')
        if input == 'both':
            self._doublecodex(fn)
        elif input in ["py", "r"]:
            snippet = fn.split("/")[-1]
            code = self._read_snippet(f"{fn}.{input}")
            language = dict(r="r", py="python")[input]
            self._code_input(f"{language.title()} code", code, language=language, snippet=snippet)
        else:
            raise Exception("?")
            lines = self._read_snippet(f"{fn}.{input}")
            name = dict(py="Python", r="R")[input]
            self._code_input(f"{name} code", lines)
        #output = kwargs.get('output', 'both')
        #format = kwargs.get('format', 'plain')
        #if output in ('r', 'py'):
        #    self._codexoutput(f"{fn}.{output}", format, caption=outputcaption(output))
        #elif output == "both":
        #    self._doubleoutput(fn, format)
        #self.emit("</div>")
        self.emit("\n:::\n:::\n")


    ##### REFERENCES #####
    def refchap(self, node, _nodes):
        self._ref(node, prefix="chap")

    def refsec(self, node, _nodes):
        self._ref(node, prefix="sec")

    def pageref(self, node, _nodes):
        raise Exception("Sorry!")
        ref = _arg(node)
        assert ref == "feature:sparse"
        return self.ref


    def reffig(self, node, _nodes):
        self._ref(node, prefix="fig")

    def refex(self, node, _nodes):
        self._ref(node, prefix="exm")

    def ref(self, node, _nodes):
        ref = _args(node)[0]
        if ":" in ref:
            prefix, ref = ref.split(":", 1)
            prefix = {'ex': 'exm'}.get(prefix, prefix)
        else:
            prefix = None
        self.emit("[-")
        self._doref(ref, prefix)
        self.emit("]")

    def _ref(self, node, prefix=None):
        self._doref(_args(node)[0], prefix=prefix)

    def _doref(self, ref, prefix=None):
        self.emit("@")
        if prefix:
            self.emit(prefix + "-")
        self.emit(ref)



    #### CITATIONS ####
    def citep(self, node, nodes):
        opt = _optargs(node)
        if len(opt) == 1:
            pre, post = "", opt[0] + " "
        elif len(opt) == 2:
            pre, post = opt[0] + " ", opt[1] + " "
        else:
            pre, post = "", ""
        self.emit("[")
        if pre and pre.strip():
            self.emit(pre)
        self.citet(node, nodes, add_parentheses=False)
        if post and post.strip():
            self.emit(post)
        self.emit("]")

    def citet(self, node, nodes, add_parentheses=True):
        arg, = _args(node)
        for i, item in enumerate(arg.split(",")):
            if i:
                self.emit(";")
            self.emit(f"@{item}")

    def citealp(self, node, nodes):
        self.citet(node, nodes, add_parentheses=False)
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
        m = re.search(r"(.*),?caption=\{([^}]+)\}(.*)", argtext)
        if m:
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

def _optargs(node) -> List[str]:
    return [str(x.string) for x in node.args if isinstance(x, BracketGroup)]


def _optarg(node) -> str:
    args = _optargs(node)
    assert len(args) == 1, f"#Optional Arguments != 1: {args} [{node}]"
    return args[0]


def _args(node) -> List[str]:
    return [str(x.string) for x in node.args if isinstance(x, BraceGroup)]


def _arg(node) -> str:
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


def _label_from_caption(caption):
    assert len(caption.args) == 1
    return _pop_named(caption.args[0]._contents, "label", strict=False)


def _pop_named(nodes, name, strict=True):
    names = [node.name for node in nodes]
    if name not in names:
        if strict:
            raise ValueError(f"{name} not in {names}: {nodes}")
        return
    return nodes.pop(names.index(name))


def preprocess(tex: str):
    verbs = []
    buffer = []
    for x in re.split(r"(\\verb\|[^|]+\||\\verb\+[^+]+\+)", tex):
        m = (re.match(r"\\verb\|([^|]+)\|", x) or re.match(r"\\verb\+([^+]+)\+", x))
        if m:
            buffer.append(f"\\verbplaceholder{{{len(verbs)}}}")
            verbs.append(m.group(1))
        else:
            m = re.match(r"\\SaveVerb\{(\w+)\}\|([^|]+)\|", x)
            if m:
                print("????", m.groups())
            else:
                buffer.append(x)
    tex = "".join(buffer)
    tex = tex.replace("\\ ", " ").replace("\\,", "").replace("on p.~\\pageref{feature:sparse}", "in \\refsec{workflow}")

    return tex, verbs

def outputcaption(lang):
    name = dict(py="Python", r="R")[lang]
    other = dict(py="R", r="Python")[lang]
    return f"{name} output. Note that {other} output may look slightly different"


def tikzfig(outf: Path, tikz: str, density=144):
    tmpdir = Path(tempfile.mkdtemp())
    logging.info(f"Creating tikz figure in {tmpdir}")
    with open(tmpdir / "test.tex", "w") as f:
        f.write("""\\documentclass{article}
                   \\usepackage{tikz}
                   \\usepackage{pgfplots}
                   \\usepackage{neuralnetwork} 
                   \\usetikzlibrary{external}
                   \\tikzexternalize
                   \\begin{document}\n\n""")
        f.write(tikz)
        f.write("\n\n\\end{document}")
    cmd = 'pdflatex -halt-on-error -interaction=batchmode -jobname "test-figure0" "\\def\\tikzexternalrealjob{test}\input{test}"'
    subprocess.check_call(cmd, shell=True, cwd=tmpdir)
    cmd = ["convert", "-density", str(density), tmpdir/'test-figure0.pdf', outf]
    subprocess.check_call(cmd)
    shutil.rmtree(tmpdir)

def read_tags(**files):
    for lang, file in files.items():
        if not file:
            continue
        for cell in json.load(open(file))['cells']:
            tags = cell.get("metadata", {}).get("tags", [])
            snippet = [t for t in tags if t.startswith("snippet:")]
            if snippet:
                yield (lang, snippet[0].replace("snippet:", "")), tags

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')
    tex = " ".join(sys.argv[1:])
    #tex = open("/home/wva/test.tex").read()
    tex, verbs = preprocess(tex)
    nodes = TexSoup.TexSoup(tex).expr._contents
    n = nodes.copy()
    p = Parser(chapter=1, sink=StringIO(), verbs=verbs, base=None, out_folder=Path("/tmp"), toc=None, bibliography=None)
    html = p.parse_str(nodes)
    print(html)
    #open("/tmp/bla.html", "w").write(html)


