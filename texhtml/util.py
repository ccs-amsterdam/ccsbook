import logging
from pathlib import Path
import re

from TexSoup import TexSoup
from TexSoup.data import BraceGroup, BracketGroup
from jinja2 import Environment, PackageLoader, select_autoescape

def read_tex(base: Path, fn: str):
    logging.info(f"Parsing {base / fn}")
    tex = open(base / fn).read()
    # Remove comments
    tex = re.sub(r"^\%.*$", "", tex, flags=re.MULTILINE)
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