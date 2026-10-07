"""Shrinks the sample receipts from PNG to JPEG and rewrites the manifest.

make_receipts.py renders flat-colour PNGs, which cost about 1.1 MB each for no
visual gain. The demo loads all seven in one click, so they ship as JPEG.

    py -3.10 tools/shrink-samples.py
"""
import json, os, re
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "samples", "receipts")
MAN = os.path.join(D, "manifest.json")

man = json.load(open(MAN, encoding="utf-8"))
out = []
for row in man:
    old = os.path.join(D, row["file"])
    base, ext = os.path.splitext(row["file"])
    new_name = base + ".jpg"
    new = os.path.join(D, new_name)
    im = Image.open(old).convert("RGB")
    im.save(new, "JPEG", quality=90, optimize=True, progressive=True)
    before, after = os.path.getsize(old), os.path.getsize(new)
    if not os.path.samefile(old, new):
        os.remove(old)
    print("%-32s %8d -> %8d  %s" % (row["file"], before, after, new_name))
    row["file"] = new_name
    out.append(row)

json.dump(out, open(MAN, "w", encoding="utf-8"), indent=2)
print("\nmanifest rewritten ->", MAN)
print("remaining files:", sorted(f for f in os.listdir(D) if not f.endswith(".json")))
