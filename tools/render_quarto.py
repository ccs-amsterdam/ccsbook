import re
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

if args.chapters:
    keep = set(args.chapters) | {int(x.name.replace("chapter", "").replace(".qmd", "")) for x in out.glob("chapter*.qmd")}
    chapters = [x for x in toc.chapters if (not args.chapters) or (int(x.nr) in keep)]
else:
    chapters = toc.chapters

(out / "_quarto.yml").open("w").write(template.render(**locals()))

shutil.copy((Path(template.filename).parent) / "index.qmd", out/"index.qmd")
shutil.copy("references.bib", out/"references.bib")
shutil.copy((Path(template.filename).parent) / "references.qmd", out/"references.qmd")

template = get_template('chapter.qmd')
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
                    base=base, out_folder=out, notebook_py=current_chapter_py, notebook_r=current_chapter_r)
    content = parser.parse_str(TexSoup(tex).expr._contents, finalize=True)
    content = re.sub(r"\s*\n\s*\n\s*", "\n\n", content)
    content = re.sub(r"\n\s*\n:::\n", "\n:::\n", content)
    content = re.sub(r"\n\s*\n:::\n", "\n:::\n", content)
    open(outf, "w").write(content)

    #if parser.unknown_nodes:
    #    unknown[chapter.nr] = parser.unknown_nodes

sys.exit()
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
