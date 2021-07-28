import re

from collections import namedtuple
from pathlib import Path

TOCEntry = namedtuple("TOCEntry", ["nr", "texfile", "fn", "label", "caption", "children"])

class TOC:
    def __init__(self, base, fn='main.aux'):
        self.labels = {} # name : number
        self.chapters = [] # (nr, ref, caption, [sections]) where section=(nr, ref, caption)
        self.reverse = {} # number : name
        self.read_structure(base, fn)

    def read_structure(self, base, fn):
        chapter = 0
        for line in open(base/fn):
            if m:=re.match(r"\\@input\{(chapter\d+)/(.*\.aux)\}", line):
                chapter += 1
                inf = base / m.group(1) / m.group(2)
                texf = inf.with_suffix(".tex")
                for line in open(inf):
                    # chance \"{i} into \"i because regex are context free grammars
                    line = re.sub(r"\\('|\")\{(\w+)\}", "\\1\\2", line)

                    if not line.startswith("\\newlabel{"):
                        continue
                    name, args = parse_braces(line)
                    number, _, caption, tocnr, _ = parse_braces(args)
                    fn = f"chapter{chapter:02d}.html"
                    entry = TOCEntry(number, texf, fn, name, caption, [])
                    if tocnr.startswith("chapter"):
                        self.chapters.append(entry)
                    elif tocnr.startswith("section"):
                        self.chapters[-1].children.append(entry)
                    self.labels[name] = number

def parse_braces(line):
    result = []
    depth = 0
    for token in re.split("([{}])", line):
        if token == "{":
            depth = depth + 1
            if depth == 1:
                result.append("")
            else:
                result[-1] += "{"
        elif token == "}":
            depth = depth - 1
            if depth > 0:
                result[-1] += "}"
        elif token and depth:
            result[-1] += token
    return result

if __name__ == '__main__':
    TOC(Path.cwd())