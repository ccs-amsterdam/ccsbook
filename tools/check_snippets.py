import sys

nerr = 0
files = set()
for f in sys.argv[1:]:
    for i, line in enumerate(open(f)):
        line = line.rstrip("\n")
        if len(line) > 50:
            print(f"[TOO LONG {len(line):3}] {f}:{i}")
            files.add(f)
            nerr += 1
        if "'" in line:
            print(f"[SINGLE QUOTE] {f}:{i}")
            nerr += 1
        if "http:" in line:
            print(f"[NO HTTPS    ] {f}:{i}")
            nerr += 1

print(f"** {nerr} problems in {len(files)} files")

