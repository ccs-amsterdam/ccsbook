from pathlib import Path
import sys

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