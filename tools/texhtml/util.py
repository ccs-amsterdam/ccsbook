import logging
from pathlib import Path
import re

from PIL import Image
from TexSoup import TexSoup
from TexSoup.data import BraceGroup, BracketGroup
from jinja2 import Environment, PackageLoader, select_autoescape





def arg(node):
    a, = args(node)
    return a

def args(node):
    if node is None:
        raise TypeError("?")
    return [re.sub(r"^{|}$", "", str(x)) for x in node.args if isinstance(x, BraceGroup)]

def optarg(node, default=None):
    opts = optargs(node)
    if opts:
        return opts[0]
    else:
        return default

def optargs(node):
    return [re.sub(r"^\[|\]$", "", str(x)) for x in node.args if isinstance(x, BracketGroup)]


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
    "\\_": "_",
    "\\$": "$",
    "\\cdot": "·",
    "\\times": "×",
    "\\textless": "&lt;",
    "\\textbar": "|",
    "\\lbrack": "[",
    "\\rbrack": "]",
    "\\textbackslash": "&bsol;",
    "\\dagger": "",
    "\\color{gray}": "",
    "\\^": "^",
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
    '\\`a': "à",
    '\\`i': "ì",
    '\\`u': "ù",
    '\\`e': "è",
    '\\=o': 'ō',
}

def clean_text(text: str) -> str:
    text = re.sub(r"(?<!\\)\$(.*?)\$", "<em>\\1</em>", text)
    for k,v in SUBS.items():
        text = text.replace(k, v)
    for k,v in ACCENTS.items():
        text = text.replace(k, v).replace(k.upper(), v.upper())
    # For some weird reason, \index(x)\emph(x) was not processed in capter 6 :(
    text = re.sub(r"\\index\{([^}]+)\}", "", text)
    text = re.sub(r"\\(emph|texttt|small|textit)\{([^}]+)\}", "\\2", text)
    text = re.sub(r"\\(textbf)\{([^}]+)\}", "<b>\\2</b>", text)
    #text = re.sub(r"\{\\color\{gray\}([^}]+)\}", "<i>\\1</i>", text)
    text = re.sub(r"\\(verb)\|([^|]+)\|", "\\2", text)
    text = re.sub(r"(https?://)(.*?)( |$)", "<a href='\\1\\2'>\\2</a>", text)
    if "\\" in text.replace("\\(", "").replace("\\)", ""):
        raise Exception(f"Unknown accent: {repr(text)}")
    return text


def thumbnail(img: Path, size=640) -> Path:
    if img.suffix != ".png":
        raise Exception("Sorry :(")
    outf = img.parent / f"{img.stem}_thumb{img.suffix}"
    if not outf.exists():
        im = Image.open(img)
        im.thumbnail((size, size))
        im.save(outf)
    return outf

def text(node):
    return "".join(node.text)