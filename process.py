import logging
import pprint
import sys
from collections import namedtuple
from itertools import takewhile
import tempfile
import subprocess
from pathlib import Path
import re
import json
from queue import Empty

from jupyter_client import KernelClient
from jupyter_client.manager import start_new_kernel

_LOG_CONTEXT = "?"
def set_log_context(context):
    global _LOG_CONTEXT
    _LOG_CONTEXT = context


def log(msg, context=None):
    if context is None:
        context = _LOG_CONTEXT
    logging.info(msg, extra=dict(context=context))


def debug(msg, context=None):
    if context is None:
        context = _LOG_CONTEXT
    logging.debug(msg, extra=dict(context=context))


def log_error(msg, context=None):
    if context is None:
        context = _LOG_CONTEXT
    logging.error(msg, extra=dict(context=context))


def run_code(kc: KernelClient, code: str, timeout=None):
    # from https://github.com/pystitch/stitch
    msg_id = kc.execute(code)
    while True:
        try:
            msg = kc.shell_channel.get_msg(timeout=timeout)
        except Empty:
            # TODO: Log error
            raise

        if msg['parent_header'].get('msg_id') == msg_id:
            break
        else:
            # not our reply
            continue

    messages = []
    while True:  # until idle message
        try:
            # We've already waited for execute_reply, so all output
            # should already be waiting. However, on slow networks, like
            # in certain CI systems, waiting < 1 second might miss messages.
            # So long as the kernel sends a status:idle message when it
            # finishes, we won't actually have to wait this long, anyway.
            msg = kc.iopub_channel.get_msg(timeout=4)
        except Empty:
            pass
            # TODO: Log error
        if msg['parent_header'].get('msg_id') != msg_id:
            # not an output from our execution
            continue

        msg_type = msg['msg_type']
        content = msg['content']

        if msg_type == 'status':
            if content['execution_state'] == 'idle':
                break
            else:
                continue
        elif msg_type == 'stream':
            log(content['text'])
        elif msg_type == 'error':
            msg = f'{content["ename"]}: {content["evalue"]}'
            raise Exception(msg)
        elif msg_type in ('execute_input', 'execute_result', 'display_data'):
            # Keep `execute_input` just for execution_count if there's
            # no result
            messages.append(msg)
        elif msg_type == 'clear_output':
            messages = []
            continue
        elif msg_type.startswith('comm'):
            continue
    return messages


_KERNELS = {}
KERNELNAMES = {"r": "ir", "py": "python"}
def get_kernel(kernel_name: str) -> KernelClient:
    global _KERNELS
    if kernel_name not in _KERNELS:
        _KERNELS[kernel_name] = start_new_kernel(kernel_name=kernel_name)
    return _KERNELS[kernel_name][1]


class Example:
    def __init__(self, name, caption=None, **options):
        self.name = name
        self.caption = caption or name
        self.options = options
        self.chunks = []

    def process_to_latex(self):
        width=".45" if len(self.chunks)>1 else ".95"
        longest_input = max(len(chunk.lines) for chunk in self.chunks)
        print("\\begin{example}")
        for chunk in self.chunks:
            print(f"\\begin{{minipage}}{{{width}\\linewidth}}")
            if self.options.get('echo', True):
                print(f"\\begin{{ex_{chunk.lang}_in}}")
                print(chunk.code)
                print("\n"*(longest_input - len(chunk.lines)), end='')
                print(f"\\end{{ex_{chunk.lang}_in}}")
            print(r"\end{minipage}")
            if self.options.get('eval', True):
                chunk.run()
        if self.options.get('keep') == 'r':
            chunks = [self.chunks[0]]
        elif self.options.get('keep') == 'py':
            chunks = [self.chunks[1]]
        else:
            chunks = self.chunks
        width=".45" if len(chunks)>1 else ".95"
        
        if self.options.get('output') != 'hide':
            for chunk in chunks:
                print(f"\\begin{{minipage}}{{{width}\\linewidth}}")
                log(f"Output: {self.options.get('output')}")
                if self.options.get('output', 'text') == 'text':
                    print(f"\\begin{{ex_{chunk.lang}_out}}")
                    for line in chunk.get_text_output():
                        print(line)
                    print(f"\\end{{ex_{chunk.lang}_out}}")
                elif self.options.get('output') == 'latex':
                    for line in chunk.get_latex_output():
                        print(line)
                elif self.options.get('output') == 'html':
                    html = "\n".join(chunk.get_html_output())
                    open(f"{self.name}.txt","w").write(html)
                    fig = convert_html_pdf(html, self.name)
                    print(f"\\includegraphics[width=\linewidth]{{{fig}}}")
                print(r"\end{minipage}")
        print(f"\\caption{{{self.caption}}}")
        print(f"\\label{{ex:{self.name}}}")
        print("\end{example}")


def pipe(command, input, **kargs):
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, **kargs)
    out, _err = proc.communicate(input)
    return out

def convert_html_pdf(html, name):
    pdf = pipe(["wkhtmltopdf", "-", "-"], html.encode('ascii', 'xmlcharrefreplace'))
    outf = Path.cwd()/"figures_generated"/f"{name}.pdf"
    log(f"Writing html image to {outf}")
    pdf = pipe(["pdfcrop", "-", str(outf)], pdf)
    return outf
        
class Chunk:
    def __init__(self, lang, **options):
        self.lang = lang
        self.options = options
        self.lines = []
        self.output = None

    @property
    def code(self):
        return "\n".join(self.lines)

    def run(self):
        kernel = get_kernel(KERNELNAMES[self.lang])
        try:
            self.output = list(run_code(kernel, self.code))
        except Exception as e:
            log_error(e)
            sys.exit(1)

    def get_text_output(self):
        assert self.output is not None
        for msg in self.output:
            #import pprint, sys; pprint.PrettyPrinter(indent=4, stream=sys.stderr).pprint(msg)
            data = msg.get('content', {}).get('data', {})
            text = msg.get('content', {}).get('text', {})
            if data:
                yield data['text/plain'].rstrip("\n")
            elif text:
                yield text.rstrip("\n")

    def get_html_output(self):
        assert self.output is not None
        for msg in self.output:
            #import pprint, sys; pprint.PrettyPrinter(indent=4, stream=sys.stderr).pprint(msg)
            if msg['msg_type'] in ('execute_result', 'display_data'):
                yield msg['content']['data']['text/html'].rstrip("\n")
        
                
    def get_latex_output(self):
        assert self.output is not None
        for msg in self.output:
            #import pprint, sys; pprint.PrettyPrinter(indent=4, stream=sys.stderr).pprint(msg)
            if msg['msg_type'] != 'display_data':
                continue
            yield msg['content']['data']['text/latex'].rstrip("\n")


def process_line(state: Example, line: str):
    m = re.match(r"%!(\w+)(\((.*)\))?", line)
    if m:
        command, _, options = m.groups()
        options = eval(f"dict({options})") if options else {} # sorry :)
        if command == "example":
            if state is not None:
                raise ValueError("Close previous example before starting new example")
            state = Example(**options)
            debug(f"Fond example {state.name}")
        elif command == "chunk":
            if state is None:
                raise ValueError("Cannot create chunk outside of example")
            state.chunks.append(Chunk(**options))
            debug(f"Found {state.chunks[-1].lang} chunk")
        elif command == "done":
            if state is None:
                raise ValueError("Cannot close example outside of example")
            log(f"Processing example {state.name} with chunks {[c.lang for c in state.chunks]}")
            state.process_to_latex()
            state = None
    elif state:
        if not state.chunks:
            raise ValueError("Cannot have text before first chunk in example")
        state.chunks[-1].lines.append(line)
    else:
        print(line)
    return state


def process_lines(file):
    state = None
    for i, line in enumerate(file):
        line = line.rstrip('\n')
        set_log_context(f"{file.name}:{i+1}")
        try:
            state = process_line(state, line)
        except Exception as e:
            log_error(f"Error while processing: {e}")
            raise


def process_file(file):
    try:
        process_lines(file)
    finally:
        for name, (manager, kernel) in _KERNELS.items():
            kernel.shutdown()
            kernel.stop_channels()
            manager.cleanup()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)-5s %(context)s] %(message)s')
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="Input file(s)")
    args = parser.parse_args()

    file = open(args.input) if args.input and args.input != "-" else sys.stdin
    process_file(file)



