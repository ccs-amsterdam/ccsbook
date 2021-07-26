import re

from tools.texhtml.util import clean_text

def read_bbl(fn) -> dict:
    current_item = None
    items = {} # key: (short, long)

    for line in open("main.bbl"):
        if current_item:
            if not line.strip():
                current_item = None
            else:
                line = clean_text(line.replace("\\newblock", "").replace("\\em", "").replace("{", "").replace("}", "")).strip()
                items[current_item][1].append(line)
        elif m := re.match(r"\\bibitem\[([^]]+)\]{([^}]+)}", line):
            short, key = m.groups()
            key = key.strip()
            current_item = key
            short = clean_text(short.replace("{", "").replace("}", "")).strip()
            items[key] = (short, [])
    return items