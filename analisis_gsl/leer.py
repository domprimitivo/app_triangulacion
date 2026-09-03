import json, sys

def leer(path):
    with open(path) as f:
        nb = json.load(f)
    print("="*90)
    print("NOTEBOOK:", path)
    print("="*90)
    for i, c in enumerate(nb.get("cells", [])):
        src = "".join(c.get("source", []))
        if not src.strip():
            continue
        t = c.get("cell_type")
        print(f"\n----- CELL {i} [{t}] -----")
        print(src)

if __name__ == "__main__":
    leer(sys.argv[1])
