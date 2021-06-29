import logging
from pathlib import Path
import argparse

from jinja2 import Template

from texhtml.parser import Parser, UnknownNode
from texhtml.toc import TOC
from texhtml.util import read_tex, get_template


logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('chapters', type=int, nargs='*')
args = parser.parse_args()

base = Path.cwd()
toc = TOC(base)
template = get_template('chapter.html')
unknown_nodes = set()
for chapnr, chapter in enumerate(toc.chapters, start=1):
    if args.chapters and chapnr not in args.chapters:
        continue
    outf = f"/tmp/{chapter.fn}"
    print(f"{chapter.nr}: {chapter.texfile} -> {outf}")
    parser = Parser(base, chapnr, toc)
    try:
        for node in read_tex(base, chapter.texfile):
            try:
                parser.parse(node)
            except UnknownNode as e:
                unknown_nodes.add(str(e))
                continue
            except:
                print(parser.buffer)
                raise

        content = parser.get_html()

        current_chapter = chapter.fn
        html = template.render(**locals())
        open(outf, "w").write(html)
    except:
        logging.exception(f"Error on parsing {chapter.texfile}")

if unknown_nodes:
    logging.warning(f"Unknown nodes: {unknown_nodes}")
