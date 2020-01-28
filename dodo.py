from pathlib import Path
from pathlib import Path
import sys
import re
from doit.tools import run_once

PYTHON="env/bin/python"

def task_process():
    for fn in Path.cwd().glob('**/*.ipynb'):
        if "/env/" in str(fn) or ".ipynb_checkpoint" in str(fn):
            continue
        yield {
            'name': fn.relative_to(Path.cwd()),
            'file_dep': [fn],
            'task_dep':['install_kernel'],
            'actions': [f"{PYTHON} jupro.py {fn}"],
            'verbosity': 2,
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
            'actions': [f"pdflatex {fn}", f"biber {fn.stem}", f"pdflatex {fn}"],
            'verbosity': 2,
            }
        



def task_install_env():
    """Install python virutal environment as needed"""
    requirements = Path("requirements.txt")
    lib = Path.cwd()/"src"/"lib"
    yield {
        'name': f"Install python dependencies in virtual environment env from {requirements}",
        'file_dep': [requirements],
        'targets': ['env'],
        'actions': ["python3 -m venv env",
                    "env/bin/pip install -U pip wheel",
                    f"env/bin/pip install -r {requirements}",
                    ],
        'verbosity': 2
    }

def task_install_kernel():
    """Install R kernel environment as needed"""
    yield {
        'name': f"Install R Kernel",
        'actions': ["(. env/bin/activate; Rscript -e 'if (!require(IRkernel)) install.packages(\"IRkernel\"); IRkernel::installspec()')"],
        'verbosity': 2,
        'uptodate': [run_once],
        'task_dep':['install_env'],
        
    }


