import re

from collections import namedtuple
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
                    if m:=re.match(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}", line):
                        #\newlabel{chap:fundata}{{2}{21}{Getting started: Fun with data and visualizations}{chapter.2}{}}
                        name=m.group(1)
                        number=m.group(2)
                        caption = m.group(4)
                        tocnr = m.group(5)
                        fn = f"chapter{chapter:02d}.html"
                        entry = TOCEntry(number, texf, fn, name, caption, [])
                        if tocnr.startswith("chapter"):
                            self.chapters.append(entry)
                        elif tocnr.startswith("section"):
                            self.chapters[-1].children.append(entry)
                        self.labels[name] = number
