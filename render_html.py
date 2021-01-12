import logging
from pathlib import Path

from jinja2 import Template

from texhtml.parser import Parser, UnknownNode
from texhtml.toc import TOC
from texhtml.util import read_tex, get_template


logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

base = Path("/home/wva/ccsbook/")
toc = TOC(base)
template = get_template('chapter.html')
unknown_nodes = set()
for i, chapter in enumerate(toc.chapters):
    #if (i+1) != 3:
    #    continue
    outf = f"/tmp/{chapter.fn}"
    print(f"{i+1}: {chapter.texfile} -> {outf}")
    parser = Parser(base, i+1, toc)
    try:
        for node in read_tex(base, chapter.texfile):
            try:
                parser.parse(node)
            except UnknownNode as e:
                unknown_nodes.add(str(e))
                continue

        content = parser.get_html()

        current_chapter = chapter.fn
        html = template.render(**locals())
        open(outf, "w").write(html)
    except:
        logging.exception(f"Error on parsing {chapter.texfile}")

if unknown_nodes:
    logging.warning(f"Unknown nodes: {unknown_nodes}")