import re

from texhtml.util import read_tex, arg


class TOC:
    def __init__(self, base, fn='main.tex'):
        self.labels = {} # name : (chapter, number)
        self.read_structure(base, fn)

    def add_label(self, name, chapter, number):
        print(name, chapter, number)
        self.labels[name] = chapter, number

    def read_structure(self, base, fn):
        # texsoup can't parse main page, so extract includes manually
        chapter = 0
        last = None
        for line in open(base/"main.tex"):
            if m:= re.match(r"^\\include{(chapter.*)}\s+$", line):
                fn = f"{m.group(1)}.tex"
                if '02' not in fn: continue
                for node in read_tex(base, fn):
                    print(node.name)
                    if node.name == "chapter":
                        chapter += 1
                        section = 0
                        ccsexample = 0
                        figure = 0
                        table = 0
                        last = f"{chapter}"
                    if node.name == "section":
                        section += 1
                        subsection = 0
                        last = f"{chapter}.{section}"
                    if node.name == "subsection":
                        subsection += 1
                        last = f"{chapter}.{section}.{subsection}"
                    if node.name == 'pyrex':
                        ccsexample += 1
                        last = f"{chapter}.{ccsexample}"
                        fn = arg(node).split("/")[-1]
                        label = f"ex:{fn}"
                        self.add_label(label, chapter, last)
                    if node.name == 'ccsexample':
                        ccsexample += 1
                        last = f"{chapter}.{ccsexample}"
                        for label in node.label:
                            self.add_label(label.text, chapter, last)
                    if node.name == "figure":
                        figure += 1
                        last = f"{chapter}.{figure}"
                        for label in node.label:
                            self.add_label(label.text, chapter, last)
                    if node.name == "table":
                        table += 1
                        last = f"{chapter}.{table}"
                        for label in node.label:
                            self.add_label(label.text, chapter, last)
                    if node.name == "label":
                        self.add_label("".join(node.text), chapter, last)
