import re
import sys
import keyword
keywords = {"py": {"!pip3", "install"} | set(keyword.kwlist),
            "r": {"colnames", "glue","print","library","install.packages",r"%>%" }}

langs = {"py": "Python", "r": "R"}

def format(snippet, lang):
    for kw in keywords[lang]:
        snippet = re.sub(f"(\\s|^|\\b)(?<!\")({kw})(\\W|$|\\b)", "\\1<spankeyword>\\2</span>\\3", snippet, flags=re.M)
    snippet = re.sub(r"\b(\w+)\(", "<spanfunction>\\1</span>(", snippet)
    snippet = re.sub(r"^#(.*)", "<spancomment>#\\1</span>", snippet, flags=re.M) 
    snippet = snippet.replace("\n", "<br/>\n").replace(" ", "&nbsp;")
    snippet = re.sub("('.*?')", "<span class='quote'>\\1</span>", snippet)
    snippet = re.sub('(".*?")', "<span class='quote'>\\1</span>", snippet)
    snippet = snippet.replace("<spankeyword>", "<span class='keyword'>")
    snippet = snippet.replace("<spanfunction>", "<span class='function'>")
    snippet = snippet.replace("<spancomment>", "<span class='comment'>")
    return snippet

def render(snippets):
    yield """
    <html>
    <head><style>
    .snippet {
    padding: .3em;
    border: 1px solid grey;
    font-family: monospace;
    font-weight: normal;
    }
    
    h1 {color: #555}
    h2 {color: #555}
    .quote {font-style: italic; color: #555}
    .keyword {font-weight: bold}
.function {font-weight: bold}
    .comment {color: #999}
    </style>
    <body>"""
    lastex = None
    for caption, title, lang, snippet in snippets:
        if caption != lastex:
            yield(f"<h1>{caption}</h1>")
            lastex = caption

        yield(f"<h2>{title}</h2>")
        yield("<div class='snippet'>")
        yield(format(snippet, lang))
        yield("</div>")
    yield("""
    </body>
    </html>""")


def check(snippet):
    for i, line in enumerate(snippet.split("\n")):
        line = line.rstrip("\n")
        if len(line) > 50:
            yield i+1, "TOO LONG"
        if "'" in line and '"' not in line:
            yield i+1, "QUOTE   "
            print()
            print(line)
            print()
        if "http:" in line:
            yield i+1, "NO HTTPS"



def get_snippets(fn):
    m = re.match(r"[^\.]+\.(py|r)(\.[^\.]+)?", fn)
    if not m:
        raise Exception(f"Cannot match {fn!r}")
    lang, x = m.groups()
    if x:
        return
    snippet = open(f"snippets/{fn}").read()
    for i, problem in check(snippet):
        print(f"[{problem}] {caption}:{i}")
    title = f"{langs[lang]} {'output' if x else 'code'}"
    yield title, lang, snippet

def output(chapter, snippets):
    print(f"** Chapter {chapter:02} ({len(snippets)} snippets)")
    html =  "\n".join(render(snippets))
    with open(f"snippet_reformat/chapter_{chapter:02}_snippets.html", "w") as f:
        f.write(html)
        

snippets = []
last_chapter = None
for line in open("main.log"):
    m = re.match(r"EXAMPLE (\d+).(\d+): code (.*)", line)
    if m:
        chapter, section, fn = m.groups()
        chapter = int(chapter)
        if chapter != last_chapter:
            if snippets:
                output(last_chapter, snippets)
                snippets = []
            last_chapter = chapter
        #caption, snippet = line.strip().split(": ", 1)
        caption = f"Example {chapter}.{section}"
        for title, lang, snippet in get_snippets(fn):
            snippets.append((caption, title, lang, snippet))
        
        #qsnippets = list(get_snippet

output(chapter, snippets)
snippets = []
