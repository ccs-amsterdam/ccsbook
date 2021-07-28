#TODO: pageref in chapter 7
#TODO: math and tikz figures in chapter 8
#TODO: saveverb in chapter 6

import base64
import logging
import re
import shutil
from pathlib import Path
from typing import Type

import sympy
from TexSoup import TexSoup
from TexSoup.utils import Token
from texhtml.toc import TOC
from texhtml.util import optarg, arg, args, next_sibling

from tools.texhtml.util import optargs, clean_text, thumbnail, text

VERBS = []

class CodexCell:
    def __init__(self, parser, type, caption, content):
        self.parser = parser
        self.type = type
        self.caption = caption
        self.content = content

    def to_html(self, neighbour=None) -> str:
        if self.type == "input":
            if neighbour and neighbour.type == "input":
                if len(self.content) < len(neighbour.content):
                    self.content += [''] * (len(neighbour.content) - len(self.content))
            return self._code_block(self.caption, self.content)
        elif self.type == "plain":
            content = self.content.replace("<", "&lt;").replace(">", "&gt;")
            return f"<pre>{content}</pre>"
        elif self.type == "png":
            return self.parser.img_html(self.content)

            #return f"<img src='data:image/png;base64, {self.content}' />"
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
        result = [f"<div class='code-double row'>\n<div class='col-xxl-5 col-xl-6 col-md-12'>",
                   row[0].to_html(row[1]),
                   "</div>\n<div class='col-md-6'>",
                   row[1].to_html(row[0]),
                   "</div></div>",
                ]
    elif len(row) == 1:
        if isinstance(row[0], str):
            result = row
        else:
            result = ["<div class='code-single'>", row[0].to_html(), "</div>"]
    else:
        raise Exception(f"Codex rows should have 1 or 2 entries, not {len(row)}")
    return "\n".join(result)

def codex_html(caption, nr, label, rows):
    buffer = [f"<div class='code-example'><h4><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>Example {nr}.</a></small><br/> {caption}</h4>"]
    buffer += [codex_row(row) for row in rows]
    buffer += ["</div>"]
    return "\n".join(buffer)



class UnknownNode(Exception):
    pass

NODE = None

class Parser:
    def __init__(self, base: Path, chapter: int,  toc: TOC, bibliography: dict, out_folder: Path, nodes=None):
        self.nodes = [] if nodes is None else nodes
        self._base = base
        self._toc = toc
        self._chapter = chapter
        self._bibliography = bibliography
        if out_folder is not None:
            self._out_folder = out_folder
            self._img_folder = self._out_folder / "img"
            self._img_folder.mkdir(parents=True, exist_ok=True)
        self.unknown_nodes = set()
        self.n_notes = 0

    def _o(self, text):
        self.buffer.append(text)

    def read_nodes(self, fn: str):
        global VERBS
        logging.info(f"Parsing {self._base / fn}")
        tex = open(self._base / fn).read()
        # Workarounds to deal (mostly) with imperfect texsoup parsing
        # store verbs and replace with placeholder command
        buffer = []
        for x in re.split(r"(\\verb\|[^|]+\||\\verb\+[^+]+\+)", tex):
            if m := (re.match(r"\\verb\|([^|]+)\|", x) or re.match(r"\\verb\+([^+]+)\+", x)):
                buffer.append(f"\\verbplaceholder{{{len(VERBS)}}}")
                VERBS.append(m.group(1))
            else:
                buffer.append(x)
        tex = "".join(buffer)
        # Remove comments
        tex = re.sub(r"^\%.*$", "", tex, flags=re.MULTILINE)
        # drop hard spaces and \, spaces
        tex = tex.replace("\\ ", " ").replace("\\,", "")
        # change \'{a} into \'a
        tex = re.sub(r"\\('|\")\{(\w+)\}", "\\1\\2", tex)
        # change d$name into d__DOLLAR__name
        tex = re.sub(r"\b(df?)$(\w)", "\\1__DOLLAR__\\2", tex)
        # tex = tex.replace(r"d$", "d__DOLLAR__").replace("df$", "df__DOLLAR__")
        ## Change \mid into | to avoid pissing off texsoup
        # tex = tex.replace(r"\\mid\b", "|")
        open("/tmp/x.tex","w").write(tex)
        root = TexSoup(tex)
        for node in root.all:
            if getattr(node, "name", None) == "input":
                fn2 = str(node.args[0]).strip("{}")
                if not fn2.endswith(".tex"):
                    fn2 = f"{fn2}.tex"
                self.read_nodes(fn2)
            else:
                self.nodes.append(node)


    def parse(self):
        buffer = []
        while self.nodes:
            x = self.parse_next()
            if x:
                buffer.append(x)
        return "".join(buffer)

    def parse_next(self):
        node = self.nodes.pop(0)
        global NODE
        NODE = node
        if node.name == "text":
            return self.text(node.text)
        elif node.name == "$":
            return self.math(node)
        elif node.name == "$$":
            return self.expression(node)
        elif hasattr(self, node.name):
            result = getattr(self, node.name)(node)
            return result
        else:
            self.unknown_nodes.add(node.name)

    def text(self, texts = None):
        if texts and not isinstance(texts, list): raise Exception(repr(texts))
        if not texts:
            texts = []
        while self.nodes and self.nodes[0].name == "text":
            n = self.nodes.pop(0)
            texts += n.text
        text = "".join(texts)
        return clean_text(text)

    # Structure
    def subsection(self, node):
        self._thesubsection += 1
        nr = f"{self._chapter}.{self._thesection}.{self._thesubsection}"
        label = nr.replace(".", "_")
        return f"<h3><small class='text-muted'><a class='anchor' href='#{label}' name='{label}'>{nr}</a></small> {args(node)[0]}</h3>"

    def paragraph(self, node):
        t = text(node).replace("\\footnotesize", "")
        return f"<b>{t}</b>"

    def math(self, node):
        text = "".join(node.text)
        return f"<code>{text}</code>"

    def expression(self, node):
        fn =  f"expr_{id(node)}.png"
        sympy.preview(str(node), viewer='file', filename=self._img_folder / fn)
        return f"<div><img src='img/{fn}' /></div>"
        #print(node.text)

    def url(self, node):
        text = "".join(node.text)
        return build_url(text)

    def cite(self, node):
        return self.citep(node)
    def citep(self, node):
        opt = optargs(node)
        if len(opt) == 1:
            pre, post = "", opt[0] + " "
        elif len(opt) == 2:
            pre, post = opt[0] + " ", opt[1] + " "
        else:
            pre, post = "", ""
        inner = self.citet(node)
        return f"({pre}{inner}{post})"
    def citet(self, node):
        refs = []
        for item in arg(node).split(","):
            short, entries = self._bibliography[item]
            entry = " ".join(entries)
            html = f'<span class="cite" title="{entry}">{short}</span>'
            refs.append(html)
        return ';'.join(refs)


    def footnote(self, node):
        print(">>> footnote")
        parser = Parser(self._base, self._chapter, self._toc, self._bibliography, self._out_folder, nodes=TexSoup(node.text).all)
        inner = parser.parse()
        if inner.startswith("http") and " " not in inner:
            inner = build_url(inner)
        self.n_notes += 1
        return f'<a tabindex="0" class="note" data-bs-trigger="focus" data-bs-toggle="popover" title="Note {self.n_notes}" data-bs-content="{inner}">[{self.n_notes}]</a>'


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
    textit=emph

    def textbf(self, node):
        return f"<b>{arg(node)}</b>"

    def ldots(self, node):
        return "..."

    def verbplaceholder(self, node):
        print(args(node))
        n = int(arg(node))
        return f"<code>{VERBS[n]}</code>"

    # def verb(self, node):
    #     # This is not parsed correctly by texsoup, so workaround
    #     verb, remainder = inline_verb(self.nodes)
    #     text = self.text([remainder])
    #     return f"{verb}\n\n{text}"

    def newpage(self, node):
        return

    def ttt(self, node):
        return f"<code>{clean_text(arg(node))}</code> "
    texttt = ttt

    def verbatim(self, node):
        return f"<pre>{node.text[0]}</pre>"
    lstlisting=verbatim

    def vspace(self, node):
        pass
    noindent = vspace

    def itemize(self, node):
        items = "\n".join(f"  <li> {text(c)}" for c in node.children)
        return f"<ul>\n{items}\n</ul>"
    def enumerate(self, node):
        items = "\n".join(f"  <li> {text(c)}" for c in node.children)
        return f"<ol>\n{items}\n</ol>"

    # Concepts
    def _concept(self, name: str):
        return f"<code>{name}</code> "

    def concept(self, node):
        return self._concept(args(node)[0])
    pkg = fn = concept

    def _fixed_concept(self, node):
        return self._concept(node.name)
    pandas = tidyverse = sklearn = numpy = _fixed_concept

    def abstract(self, node):
        caption = arg(node)
        text = node.text[1]
        return f"<div class='abstract'><span class='caption'>{caption}</span> {text}</div>"

    def objectives(self, node):
        items = '\n'.join(f"<li>{item.text[0]}" for item in node)
        return f"<div class='objectives'><div class='caption'>Chapter objectives:</div><ul>{items}</ul></div>"

    def feature(self, node):
        print(">>> feature")

        parser = Parser(self._base, self._chapter, self._toc, self._bibliography, self._out_folder, nodes=list(node.all))
        inner = parser.parse()
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
        if label:
            label = f"{label} "
        return f"<a href='{file}#{ref}'>{label}{nr}</a>"

    def refex(self, node):
        return self._ref("Example", f"ex:{arg(node)}")

    def refchap(self, node):
        return self._ref("Chapter", f"chap:{arg(node)}")

    def refsec(self, node):
        return self._ref("Section", f"sec:{arg(node)}")

    def reftab(self, node):
        return self._ref("Table", f"tab:{arg(node)}")
    def reffig(self, node):
        return self._ref("Figure", f"fig:{arg(node)}")

    def ref(self, node):
        return self._ref("", f"{arg(node)}")


    def label(self, node):
        return  # (handled via TOC)
    def index(self, node):
        return  # (not needed)

    # Code snippets
    def _code_input(self, fn, caption):
        snippet_file = self._base / "snippets" / f"{fn}"
        code = snippet_file.open().read()
        lines = [x.replace("<", "&lt;").replace(">", "&gt;")
                 for x in code.split("\n")]
        return CodexCell(self, "input", caption, lines)

    def _code_output(self, fn, caption, format):
        suffix = dict(plain=".out", png=".png", table=".table.html")[format]
        out_file = self._base / "snippets" / f"{fn}{suffix}"
        if format == "png":
            #png = out_file.open("rb").read()
            #result = base64.b64encode(png).decode('ascii')
            result = out_file
        else:
            result = out_file.open().read()
        return CodexCell(self, format, caption, result)

    def pyrex(self, node):
        fn = arg(node)
        label = f"ex:{Path(fn).name}"
        opts = self.kwargs(node)
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

    def kwargs(self, node):
        # TODO: handle braces correctly :(
        result = {}
        argtext = optarg(node)
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

    def ccsexample(self, node):
        rows = []
        caption = arg(node.caption)
        label = arg(node.label)
        nr = self._toc.labels[label]
        logging.debug(f"Processing ccsexample {nr}:{caption}")
        for child in node:
            if isinstance(child, str):
                rows.append([child])
                continue
            #print(">>>", type(child), repr(child))
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

    # Figures
    def figure(self, node):
        nodes = {n.name: n for n in node.all}
        if "feature" in nodes:
            # Not actually a figure, but a 'feature' that was supposed to be floating
            return self.feature(nodes["feature"])
        caption = "".join(nodes['caption'].text)
        if 'label' not in nodes:
            logging.error(f"Cannot find label in figure {caption}")
            return
        ref = "".join(nodes['label'].text)
        nr = self._toc.labels[ref]
        img = Path(arg(nodes['includegraphics']))
        if img.suffix in (".pdf", ".eps"):
            img = img.with_suffix(".png")
        outf = self._img_folder / img.name
        shutil.copy(self._base / img, outf)
        thumb = thumbnail(outf)
        return f'''
        <div class='figure'>
        <h4><small class='text-muted'><a class='anchor' href='#{ref}' name='{ref}'>Fig. {nr}</a></small> {caption}</h3>
        {self.img_html(img)}  
        </div>
        '''

    def table(self, node):
        nodes = {n.name: n for n in node.all}

        caption, body, notes = args(nodes['caption'])
        if not (m := re.match(r"\\label\{([^}]+)\}(.*)", caption)):
            raise Exception(f"Cannot parse table caption: {caption}")
        ref, caption = m.groups()
        print(">>> table")
        table = parse(body + "}")
        nr = self._toc.labels[ref]
        return f'''
                <div class='figure'>
                <h4><small class='text-muted'><a class='anchor' href='#{ref}' name='{ref}'>Table {nr}</a></small> {caption}</h3>
                {table}  
                </div>
                '''

    def tabularx(self, node):
        nodes = list(node.contents)
        _width = nodes.pop(0)
        coldef = nodes.pop(0)
        head, body = [[""]], [[""]]
        target = head
        while nodes:
            n = nodes.pop(0)
            if isinstance(n, str):
                for x in re.split(r"(&|\\\\)", n):
                    x = x.strip()
                    if x == "&":
                        target[-1].append("")
                    elif x == "\\\\":
                        target.append([""])
                    else:
                        if x and not re.match("\([lr]+\)", x):
                            target[-1][-1] += x
            else:
                if n.name == "verbplaceholder":
                    verb = VERBS[int(arg(n))]
                    target[-1][-1] += f"<code>{verb}</code>"
                elif n.name == "midrule":
                    target = body
                elif n.name == "multicolumn":
                    cols, just, text = args(n)
                    target[-1][-1] += f"<th colspan='{cols}'>{text}</th>"
        html = ["<table class='table'><thead>"]
        def td(x, tag):
            if not x.startswith("<th"):
                x = f"<{tag}>{x}</{tag}>"
            return f"    {x}"

        for row in head:
            if "".join(row).strip():
                row = row + [''] * (len(coldef) - len(row))
                html += ["  <tr>"] + [td(cell, "th") for cell in row] + ["  </tr>"]
        html += ["</thead><tbody>"]
        for row in body:
            if "".join(row).strip():
                row = row + [''] * (len(coldef) - len(row))
                html += ["  <tr>"] + [td(cell, "td") for cell in row] + ["  </tr>"]
        html += ["</tbody></table>"]
        return "\n".join(html)

    def img_html(self, img: Path):
        outf = self._img_folder / img.name
        shutil.copy(self._base / img, outf)
        thumb = thumbnail(outf)
        return f"""<a href='img/{img.name}' title='Click to open full-size image'>
        <img src='img/{thumb.name}' />   
        </a> """


def parse(tex: str):
    parser = Parser(None, None, None, None, None, nodes=TexSoup(tex).all)
    return parser.parse()

def build_url(link, text=None):
    if text is None:
        text = link.replace("https://", "").replace("http://", "")
    return f"<a href='{link}'>{text}</a>"

def inline_verb(nodelist):
    text = "".join(nodelist.pop(0).text)
    verb_char = text[0]
    text = text[1:]
    if verb_char not in "+|":
        raise ValueError(f"Unexpected verbatim input: {text}")
    to = text.find(verb_char)
    while to == -1:
        n = nodelist.pop(0)
        text += "".join(n.text)
        to = text.find(verb_char)
    verb_text = text[:to].replace("__DOLLAR__", "$")
    remainder = text[(to + 1):]
    return f"<code>{verb_text}</code>", remainder