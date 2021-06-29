import sys

for f in sys.argv[1:]:
    for i, line in enumerate(open(f)):
        line = line.rstrip("\n")
        if len(line) > 50:
            print(f"[{len(line):3}] {f}:{i}")

