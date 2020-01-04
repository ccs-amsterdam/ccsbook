import json
import logging
from pathlib import Path
import subprocess


def run_notebook(fn: Path) -> dict:
    """Run a notebook, returning the raw json dict"""
    cmd = ["env/bin/jupyter", "nbconvert", "--to", "notebook", "--stdout", str(fn)]
    out = subprocess.check_output(cmd)
    return json.loads(out)


def create_snippets(fn: Path):
    nb = run_notebook(fn)
    ext = nb["metadata"]["language_info"]["file_extension"]
    out_folder = Path.cwd()/"snippets"/fn.parent.name
    out_folder.mkdir(exist_ok=True, parents=True)
    logging.info(f"Writing output to {out_folder}/")

    for cell in read_cells(nb):
        name = cell.snippet_name
        if cell.cell_type == "code" and name:
            logging.info(f"Found snippet: {name}")
            write(out_folder/f"{name}{ext}", cell.source)
            write(out_folder/f"{name}{ext}.out", cell.text_output())
            if 'html' in cell.requested_output:
                write_pdf_from_html(out_folder/f"{name}{ext}.html.pdf", cell.html_output())


def write(file: Path, text: str):
    logging.info(f"Writing {file}")
    with file.open("w") as f:
        f.write(text)


def pipe(command, input, **kargs):
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, **kargs)
    out, _err = proc.communicate(input)
    return out


def write_pdf_from_html(file: Path, html: str):
    pdf = pipe(["wkhtmltopdf", "-", "-"], html.encode('ascii', 'xmlcharrefreplace'))
    logging.info(f"Writing html image to {file}")
    pdf = pipe(["pdfcrop", "-", str(file)], pdf)
    
        
class Cell:
    """class representing a jupyter cell"""
    def __init__(self, data):
        self.data = data

    def tags(self, filter=None):
        tags = self.data['metadata'].get('tags', [])
        if filter:
            if not filter.endswith(":"):
                filter = f"{filter}:"
            tags = [t[len(filter):] for t in tags if t.startswith(filter)]
        return tags

    @property
    def cell_type(self):
        return self.data['cell_type']
    
    @property
    def source(self):
        return "".join(self.data["source"])

    @property
    def snippet_name(self):
        snippets = self.tags(filter="snippet")
        if len(snippets) > 1:
            raise ValueError(f"Don't use multiple snippet tags! {snippets}")
        if snippets:
            return snippets[0]
        
    @property
    def requested_output(self):
        return self.tags(filter="output")

    def get_outputs(self):
        otypes = [o['output_type'] for o in self.data['outputs']]
        if len(otypes) != len(set(otypes)):
            raise ValueError("output_types are not unique... :-( ")
        return {o['output_type']: o for o in self.data['outputs']}
    
    def get_output(self, *output_types):
        outputs = self.get_outputs()
        for t in output_types:
            if t in outputs:
                return outputs[t]
    
    def text_output(self):
        d = self.get_output("execute_result", "display_data", "stream")
        data = d.get('data', {})
        text = d.get('text', {})
        if data:
            return "".join(data['text/plain']).rstrip("\n")
        elif text:
            try:
                return text.rstrip("\n")
            except:
                return "\n".join(text).rstrip("\n")

    def html_output(self):
        d = self.get_output("execute_result", "display_data")
        #import pprint, sys; pprint.PrettyPrinter(indent=4, stream=sys.stderr).pprint(d)
        return "\n".join(d['data']['text/html']).strip()


    

def read_cells(nb: dict):
    for cell in nb['cells']:
        yield Cell(cell)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)-5s] %(message)s')
    import sys
    create_snippets(Path(sys.argv[1]))