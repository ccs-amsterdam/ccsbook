import logging
import shutil
from io import StringIO
from pathlib import Path
import argparse

from TexSoup import TexSoup
from jinja2 import Template

from texhtml.texparser import preprocess, Parser
from texhtml.toc import TOC
from texhtml.util import get_template
from tools.readbbl import read_bbl

logging.basicConfig(level=logging.INFO, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

parser = argparse.ArgumentParser(description='Convert CCS book latex into HTML')
parser.add_argument('chapters', type=int, nargs='*')
args = parser.parse_args()

bibliography = read_bbl("main.bbl")

base = Path.cwd()
out = Path("/tmp/book")
out.mkdir(exist_ok=True)
toc = TOC(base)
template = get_template('chapter.html')

css_out = out / "ccsbook.css"
if not css_out.exists():
    css_in = Path(template.filename).parent / "ccsbook.css"
    shutil.copy(css_in, css_out)

#list(read_tex(base, "chapter08/test.tex"))
#import sys; sys.exit()
unknown = {}
for chapnr, chapter in enumerate(toc.chapters, start=1):
    if args.chapters and chapnr not in args.chapters:
        continue
    outf = out / chapter.fn
    print(f"{chapter.nr}: {chapter.texfile} -> {outf}")
    current_chapter = chapter.fn
    with open(chapter.texfile) as source:
        tex, verbs = preprocess(source.read())

    parser = Parser(chapter=chapnr, toc=toc, bibliography=bibliography, verbs=verbs,
                    base=base, out_folder=out)
    content = parser.parse_str(TexSoup(tex).expr._contents)
    html = template.render(**locals())
    open(outf, "w").write(html)

    #if parser.unknown_nodes:
    #    unknown[chapter.nr] = parser.unknown_nodes

if unknown:
    for chapter, missing in unknown.items():
        logging.warning(f"Chapter {chapter} Unknown nodes: {missing}")
