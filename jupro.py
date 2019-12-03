import json
from pathlib import Path
from subprocess import check_output


def run_notebook(fn: Path) -> dict:
    """Run a notebook, returning the raw json dict"""
    cmd = ["env/bin/jupyter", "nbconvert", "--to", "notebook", "--stdout", str(fn)]
    out = check_output(cmd)
    return json.loads(out)

def 

if __name__ == '__main__':
    import sys
    result = run_notebook(sys.argv[1])
    print(json.dumps(result, indent=2))