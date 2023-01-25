import logging
import shutil
import sys
from io import StringIO
from pathlib import Path
import argparse

from TexSoup import TexSoup
from jinja2 import Template

from tools.texquarto.texparser import preprocess, Parser
from tools.texquarto.toc import TOC
from tools.texquarto.util import get_template
from tools.readbbl import read_bbl

logging.basicConfig(level=logging.INFO, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

parser = argparse.ArgumentParser(description='Convert CCS book latex into Quarto')
parser.add_argument('chapters', type=int, nargs='*')
args = parser.parse_args()

bibliography = read_bbl("main.bbl")

base = Path.cwd()
out = base / "quarto"
out.mkdir(exist_ok=True)
toc = TOC(base)
template = get_template('_quarto.yml')
chapters = [x for x in toc.chapters if (not args.chapters) or (int(x.nr) in args.chapters)]
(out / "_quarto.yml").open("w").write(template.render(**locals()))

unknown = {}
for chapnr, chapter in enumerate(toc.chapters, start=1):
    if args.chapters and chapnr not in args.chapters:
        continue
    prevchap = toc.chapters[chapnr-2] if chapnr > 1 else None
    nextchap = toc.chapters[chapnr] if chapnr < len(toc.chapters) else None
    outf = out / chapter.fn
    print(f"{chapter.nr}: {chapter.texfile} -> {outf}")
    current_chapter = chapter.fn
    current_chapter_py = None if chapnr == 1 else f"chapter{chapnr:02}/chapter_{chapnr:02}_py.ipynb"
    current_chapter_r = None if chapnr == 1 else f"chapter{chapnr:02}/chapter_{chapnr:02}_r.ipynb"
    with open(chapter.texfile) as source:
        tex, verbs = preprocess(source.read())

    parser = Parser(chapter=chapnr, toc=toc, bibliography=bibliography, verbs=verbs,
                    base=base, out_folder=out)
    content = parser.parse_str(TexSoup(tex).expr._contents)
    html = template.render(**locals())
    open(outf, "w").write(html)

    #if parser.unknown_nodes:
    #    unknown[chapter.nr] = parser.unknown_nodes

print(f"** Index")
current_chapter = "index"
inf = get_template("index.html")
outf = out / "index.html"
current_chapter_py = current_chapter_r = None
html = inf.render(**locals())

outf.open("w").write(html)

if unknown:
    for chapter, missing in unknown.items():
        logging.warning(f"Chapter {chapter} Unknown nodes: {missing}")
