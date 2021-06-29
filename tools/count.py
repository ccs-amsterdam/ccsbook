from pathlib import Path

cmp = Path("/home/wva/tmp/ccsbook")

def count(path):
    total = 0
    for file in path.glob("*.tex"):
        with file.open() as f:
            ln = len(f.read().split())
            total += ln
    return total



for chapter in sorted(Path.cwd().glob("chapter*")):
    nr = int(chapter.name.replace("chapter", ""))
    if nr > 14: nr += 2
    elif nr > 4: nr += 1
    
             
    other = cmp / f"chapter{nr:02}"
    if not other.exists():
        raise Exception()
    wc1 = count(chapter)
    wc2 = count(other)
    diff = wc2 - wc1
    print(f"{diff:5} {wc1:5} / {wc2:5}: {chapter.name} (was {other.name})")
    

    

