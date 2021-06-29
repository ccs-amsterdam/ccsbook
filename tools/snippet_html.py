import re
import sys
import keyword

keywords = {"py": {"!pip3", "install"} | set(keyword.kwlist),
            "r": {"colnames", "glue","print","library","install.packages",r"%>%" }}

langs = {"py": "Python", "r": "R"}

print("""
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
<body>""")

lastex = None
for line in sys.stdin:
    caption, snippet = line.strip().split(": ", 1)
    if caption != lastex:
        print(f"<h1>{caption}</h1>")
        lastex = caption
    type, fn = snippet.split(" ", 1)
    m = re.match(r"[^\.]+\.(py|r)(\.[^\.]+)?", fn)
    if not m:
        raise Exception(f"Cannot match {fn!r}")
    lang, x = m.groups()
    
    if type == "code" and not x:
        print(f"<h2>{langs[lang]} {'output' if x else 'code'}</h2>")
        print("<div class='snippet'>")
        snippet = open(f"snippets/{fn}").read()
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

        print(snippet)
        print("</div>")
              

print("""
</body>
</html>""")
