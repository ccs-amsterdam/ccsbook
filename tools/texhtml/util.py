import logging
from pathlib import Path
import re

from PIL import Image
from TexSoup import TexSoup
from TexSoup.data import BraceGroup, BracketGroup
from jinja2 import Environment, PackageLoader, select_autoescape

def read_tex(base: Path, fn: str):
    logging.info(f"Parsing {base / fn}")
    tex = open(base / fn).read()
    # Workarounds to deal (mostly) with imperfect texsoup parsing
    # Remove comments
    tex = re.sub(r"^\%.*$", "", tex, flags=re.MULTILINE)
    # drop hard spaces and \, spaces
    tex = tex.replace("\\ ", " ").replace("\\,", "")
    # change \'{a} into \'a
    tex = re.sub(r"\\'\{(\w+)\}", "\\'\\1", tex)
    # change d$name into d__DOLLAR__name
    tex = tex.replace("d$name", "d__DOLLAR__name")
    root = TexSoup(tex)
    for node in root.all:
        if getattr(node, "name", None) == "input":
            fn2 = str(node.args[0]).strip("{}")
            if not fn2.endswith(".tex"):
                fn2 = f"{fn2}.tex"
            yield from read_tex(base, fn2)
        else:
            yield node



def arg(node):
    a, = args(node)
    return a

def args(node):
    return [str(x).strip("{}") for x in node.args if isinstance(x, BraceGroup)]

def optarg(node, default=None):
    opts = [str(x).strip("[]") for x in node.args if isinstance(x, BracketGroup)]
    if opts:
        return opts[0]
    else:
        return default

def optargs(node):
    return [str(x).strip("[]") for x in node.args if isinstance(x, BracketGroup)]

def next_sibling(node):
    # The texsoup API doesn't really collaborate on this one...
    children = node.parent.children
    j, = [i for (i, x) in enumerate(children) if x.position == node.position]
    if j < len(children):
        return children[j+1]

def get_template(name):
    env = Environment(
        loader=PackageLoader('texhtml', 'templates'),
        autoescape=select_autoescape(['html', 'xml'])
    )
    return env.get_template(name)

SUBS = {
    "\n\n": "</p>\n\n<p>",
    "\\\\": "<br/>",
    "~": "&nbsp;",
    "\\&": "&amp;",
    '``': '&ldquo;',
    "''": '&rdquo;',
    "\\#": '#',
    "\\{": "{",
    "\\}": "}",
    "\\%": "%",
    "__DOLLAR__": "$",
    "\\$": "$",
}

ACCENTS = {
    "\\'a": "á",
    "\\'i": "í",
    "\\'\\i": "í",
    "\\'u": "ú",
    "\\'e": "é",
    "\\'o": "ó",
    '\\"a': "ä",
    '\\"i': "ï",
    '\\"u': "ü",
    '\\"e': "ë",
    '\\"o': "ö",
}

def clean_text(text: str) -> str:
    for k,v in SUBS.items():
        text = text.replace(k, v)
    for k,v in ACCENTS.items():
        text = text.replace(k, v).replace(k.upper(), v.upper())
    if "\\" in text:
        raise Exception(f"Unknown accent: {repr(text)}")
    return text


def thumbnail(img: Path, size=640) -> Path:
    outf = img.parent / f"{img.stem}_thumb{img.suffix}"
    if not outf.exists():
        im = Image.open(img)
        im.thumbnail((size, size))
        im.save(outf)
    return outf

def text(node):
    return "".join(node.text)