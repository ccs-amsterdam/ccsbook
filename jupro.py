import json
import logging
from pathlib import Path
from subprocess import check_output


def run_notebook(fn: Path) -> dict:
    """Run a notebook, returning the raw json dict"""
    cmd = ["env/bin/jupyter", "nbconvert", "--to", "notebook", "--stdout", str(fn)]
    out = check_output(cmd)
    return json.loads(out)

def snippet_name(cell: dict):
    tags = cell['metadata'].get('tags')
    if tags:
        snippets = [t[len("snippet:"):] for t in tags if t.startswith("snippet:")]
        if len(snippets) > 1:
            raise ValueError(f"Don't use multiple snippet tags! {snippets}")
        return snippets[0]


def create_snippets(fn: Path):
    nb = run_notebook(fn)
    ext = nb["metadata"]["language_info"]["file_extension"]
    out_folder = fn.parent/"snippets"
    out_folder.mkdir(exist_ok=True)

    for cell in nb['cells']:
        tags = cell['metadata'].get('tags', [])
        snippets = [t.replace("snippet:", "") for t in tags if t.startswith("snippet:")]
        name = snippet_name(cell)
        if cell["cell_type"] == "code" and name:
            logging.info(f"Found snippet: {name}")
            write_source(cell, out_folder/f"{name}{ext}")
            write_output(cell, out_folder/f"{name}{ext}.out")


def write(file: Path, text: str):
    logging.info(f"Writing {file}")
    with file.open("w") as f:
        f.write(text)


def write_source(cell: dict, out: Path):
    write(out, "".join(cell["source"]))


def text_output(cell: dict) -> str:
    display = [o for o in cell['outputs'] if o['output_type'] in {"execute_result", "display_data", "stream"}]
    if len(display) != 1:
        print(json.dumps(cell, indent=2), file=sys.stderr)
        raise ValueError("Cannot parse cell")
    d = display[0]
    data = d.get('data', {})
    text = d.get('text', {})
    if data:
        return "".join(data['text/plain']).rstrip("\n")
    elif text:
        try:
            return text.rstrip("\n")
        except:
            return "\n".join(text).rstrip("\n")

def write_output(cell: dict, out: Path):
    write(out, text_output(cell))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)-5s] %(message)s')
    import sys
    create_snippets(Path(sys.argv[1]))
