from pathlib import Path
import sys
import re

PYTHON="env/bin/python"

def task_process():
    for fn in Path.cwd().glob('**/*.tex.in'):
        outf = fn.parent/fn.stem
        yield {
            'name': f"Process {fn} -> {outf}",
            'file_dep': [fn],
            'targets': [outf],
            'actions': [f"{PYTHON} process.py {fn} > {outf}"],
        }
        
def _tex_deps(wd: Path, fn: Path, seen=None):
    if fn in seen:
        return
    seen.add(fn)
    for line in fn.open():
        m = re.match(r"\\(include|input){(.*?)}", line)
        if m:
            dep = wd.parent / m.group(2)
            if not dep.suffix == ".tex":
                dep = dep.parent / f"{dep.name}.tex"
            yield dep
            if dep.exists():
                yield from _tex_deps(wd, dep, seen)
        

def tex_deps(fn: Path):
    yield from _tex_deps(fn, fn, set())
    
def task_tex():
    for fn in Path.cwd().glob("*.tex"):
        if "\\documentclass" not in fn.open().read():
            continue
        outf = fn.parent/ f"{fn.stem}.pdf"
        yield {
            'basename': str(outf.relative_to(Path.cwd())),
            'file_dep': [fn] + list(tex_deps(fn)),
            'targets': [outf],
            'actions': [f"pdflatex {fn}"],
            'verbosity': 2,
            }
        
