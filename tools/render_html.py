import logging
from pathlib import Path
import argparse

from jinja2 import Template

from texhtml.parser import Parser, UnknownNode
from texhtml.toc import TOC
from texhtml.util import read_tex, get_template
from tools.readbbl import read_bbl

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

parser = argparse.ArgumentParser(description='Convert CCS book latex into HTML')
parser.add_argument('chapters', type=int, nargs='*')
args = parser.parse_args()

bibliography = read_bbl("main.bbl")

base = Path.cwd()
out = Path("/tmp/book")
toc = TOC(base)
template = get_template('chapter.html')
for chapnr, chapter in enumerate(toc.chapters, start=1):
    if args.chapters and chapnr not in args.chapters:
        continue
    outf = out / chapter.fn
    print(f"{chapter.nr}: {chapter.texfile} -> {outf}")
    nodes = list(read_tex(base, chapter.texfile))
    parser = Parser(nodes, base, chapnr, toc, bibliography, out)
    content = parser.parse()

    current_chapter = chapter.fn
    html = template.render(**locals())
    open(outf, "w").write(html)

    if parser.unknown_nodes:
         logging.warning(f"Chapter {chapter.nr} Unknown nodes: {parser.unknown_nodes}")
