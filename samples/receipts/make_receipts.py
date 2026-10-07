#!/usr/bin/env python3
"""Generate 7 synthetic 'phone photo of a paper receipt' demo images + manifest.json.

Run with:  py -3.10 make_receipts.py
Requires Pillow. No other deps (no numpy) -- uses PIL's Image.effect_noise for grain.

All merchants / addresses / transaction numbers are INVENTED for the demo.
No real company, no real logo, no machine-readable barcode.
"""
import os
import json
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = r"C:/Windows/Fonts"
W, H = 900, 1200  # portrait phone-photo frame
PAPER_W, PAPER_H = 620, 880
MARGIN = 48

FONTSETS = {
    "consolas": ("consola.ttf", "consolab.ttf"),
    "courier":  ("cour.ttf",    "courbd.ttf"),
    "arial":    ("arial.ttf",   "arialbd.ttf"),
}


def font(fname, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, fname), size)


# ---------------------------------------------------------------------------
# Receipt definitions.  total MUST equal sum(items) + tax for every receipt.
# ---------------------------------------------------------------------------
RECEIPTS = [
    dict(
        file="IMG_20260214_093012.png", merchant="NORTHSIDE COFFEE CO.",
        addr="88 NORTHSIDE AVE, PORTLAND", date="2026-02-14", txn="4821",
        items=[("FLAT WHITE", "4.50"), ("BEAN BAG 250G", "9.25")],
        tax=5.00, total=18.75, fontset="consolas",
        tint=(250, 247, 238), surface=(64, 62, 60), angle=3.1,
        grain=18, fmt="PNG",
    ),
    dict(
        file="IMG_20260218_181244.png", merchant="HARBOUR HARDWARE",
        addr="12 HARBOUR RD, DOCKLANDS", date="2026-02-18", txn="7390",
        items=[("CORDLESS DRILL", "89.95"), ("WOOD SCREWS 500", "32.35"),
               ("PAINT TRAY", "20.00")],
        tax=0.00, total=142.30, fontset="courier",
        tint=(245, 242, 232), surface=(58, 58, 64), angle=4.6,
        grain=20, fmt="PNG",
    ),
    dict(
        file="2026-03-02_fuel.jpg", merchant="KINGSWAY FUEL STOP",
        addr="404 KINGSWAY, WEST GATE", date="2026-03-02", txn="2211",
        items=[("DIESEL    49.00 L @ 1.600", "78.40")],
        tax=0.00, total=78.40, fontset="arial",
        tint=(252, 250, 243), surface=(74, 70, 66), angle=2.4,
        grain=24, fmt="JPEG",
    ),
    dict(
        file="Scan_20260305-1420.png", merchant="MERIDIAN OFFICE SUPPLY",
        addr="7 MERIDIAN WAY, UNIT 3", date="2026-03-05", txn="5560",
        items=[("A4 COPY PAPER 5RM", "39.99"), ("BALLPOINT PENS x12", "20.00")],
        tax=5.00, total=64.99, fontset="consolas",
        tint=(244, 240, 230), surface=(92, 88, 80), angle=2.0,
        grain=16, fmt="PNG",
    ),
    dict(
        file="IMG_20260311_120501.png", merchant="BLUE ANCHOR CAFE",
        addr="23 QUAY ST, OLD HARBOUR", date="2026-03-11", txn="8842",
        items=[("SOUP OF THE DAY", "9.50"), ("FISH & CHIPS", "12.00"),
               ("FILTER COFFEE", "5.00")],
        tax=0.00, total=26.50, fontset="courier",
        tint=(249, 246, 237), surface=(54, 56, 62), angle=5.3,
        grain=19, fmt="PNG",
    ),
    dict(
        file="receipt-novaprint-mar14.png", merchant="NOVAPRINT DIGITAL",
        addr="150 INDUSTRY PARK, BLDG B", date="2026-03-14", txn="6107",
        items=[("BANNER PRINT 2M", "305.00")],
        tax=5.00, total=310.00, fontset="arial",
        tint=(247, 244, 234), surface=(60, 62, 58), angle=3.8,
        grain=21, fmt="PNG",
    ),
    dict(
        file="IMG_20260320_081500.png", merchant="KINGSWAY FUEL STOP",
        addr="404 KINGSWAY, WEST GATE", date="2026-03-20", txn="3390",
        items=[("UNLEADED  44.50 L @ 1.600", "71.20")],
        tax=0.00, total=71.20, fontset="consolas",
        tint=(251, 249, 241), surface=(78, 74, 68), angle=4.2,
        grain=22, fmt="PNG",
    ),
]


def draw_receipt(spec):
    """Render the paper (before rotation) as an RGB image."""
    reg, bold = FONTSETS[spec["fontset"]]
    paper = Image.new("RGB", (PAPER_W, PAPER_H), spec["tint"])
    d = ImageDraw.Draw(paper)

    f_merch = font(bold, 27)
    f_small = font(reg, 18)
    f_body = font(reg, 21)
    f_money = font(bold, 21)
    ink = (32, 30, 28)
    dim = (78, 74, 70)

    def centered(text, f, y, col=ink):
        w = d.textlength(text, font=f)
        d.text(((PAPER_W - w) / 2.0, y), text, font=f, fill=col)
        return y + f.size + 8

    def twocol(left, right, f, y, col=ink):
        d.text((MARGIN, y), left, font=f, fill=col)
        w = d.textlength(right, font=f)
        d.text((PAPER_W - MARGIN - w, y), right, font=f, fill=col)
        return y + f.size + 9

    def sep(y):
        cw = d.textlength("-", font=f_small)
        n = int((PAPER_W - 2 * MARGIN) / cw)
        d.text((MARGIN, y), "-" * n, font=f_small, fill=dim)
        return y + f_small.size + 8

    y = 56
    y = centered(spec["merchant"], f_merch, y)
    y = centered(spec["addr"], f_small, y, dim)
    y += 4
    y = sep(y)
    y = twocol("DATE", spec["date"], f_body, y)
    y = twocol("TXN", spec["txn"], f_body, y)
    y = sep(y)

    subtotal = 0.0
    for desc, amt in spec["items"]:
        subtotal += float(amt)
        y = twocol(desc, amt, f_body, y)
    subtotal = round(subtotal, 2)

    y = sep(y)
    y = twocol("SUBTOTAL", "%.2f" % subtotal, f_body, y)
    y = twocol("TAX", "%.2f" % spec["tax"], f_body, y)
    y = twocol("TOTAL", "$%.2f" % spec["total"], f_money, y)
    y = sep(y)
    y = centered("THANK YOU", f_small, y, dim)

    # sanity: printed total must equal line items + tax
    assert abs(subtotal + spec["tax"] - spec["total"]) < 0.005, spec["file"]

    # paper texture: faint noise on the sheet only
    noise = Image.effect_noise((PAPER_W, PAPER_H), 12).convert("RGB")
    paper = Image.blend(paper, noise, 0.05)
    # re-draw text lightly blurred for print softness handled at composite time
    return paper


def build(spec, rng):
    surface = Image.new("RGB", (W, H), spec["surface"])
    # subtle lighting gradient on the surface
    grad = Image.linear_gradient("L").resize((W, H))
    grad = grad.point(lambda v: int(40 + v * 0.25))
    surface = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)),
                              surface, grad.point(lambda v: int(v * 0.35)))

    paper = draw_receipt(spec)
    paper = paper.convert("RGBA")
    angle = spec["angle"] + rng.uniform(-0.6, 0.6)
    rot = paper.rotate(angle, resample=Image.BICUBIC, expand=True)
    px = (W - rot.width) // 2 + rng.randint(-12, 12)
    py = (H - rot.height) // 2 + rng.randint(-12, 12)

    # soft drop shadow
    alpha = rot.split()[3]
    sh = Image.new("L", (W, H), 0)
    sh.paste(alpha, (px + 10, py + 16))
    sh = sh.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.55))
    surface.paste((0, 0, 0), (0, 0, W, H), sh)

    surface.paste(rot, (px, py), rot)

    # sensor/JPEG grain over the whole frame
    noise = Image.effect_noise((W, H), spec["grain"]).convert("RGB")
    img = Image.blend(surface, noise, 0.055)

    # mild vignette
    vg = Image.radial_gradient("L").resize((W, H))
    vg = vg.point(lambda v: 255 - int(v * 0.35))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(img, dark, vg)

    return img


def main():
    rng = random.Random(20260320)
    manifest = []
    for spec in RECEIPTS:
        img = build(spec, rng)
        path = os.path.join(OUT_DIR, spec["file"])
        if spec["fmt"] == "JPEG":
            img.save(path, "JPEG", quality=86)
        else:
            img.save(path, "PNG")
        manifest.append({
            "file": spec["file"],
            "merchant": spec["merchant"],
            "date": spec["date"],
            "total": spec["total"],
            "tax": spec["tax"],
        })
        print("wrote %s (%dx%d)" % (spec["file"], img.width, img.height))

    manifest.sort(key=lambda m: m["date"])
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print("wrote manifest.json with %d entries" % len(manifest))


if __name__ == "__main__":
    main()
