"""Build assets/og-card.png — the 1200x630 Open Graph / Twitter card.

The strip across the bottom is a real render of page 1 of the tool's own output
(downloads/receipts-sample.pdf): the same paper/ink palette as the site, so the
card reads as one thing rather than a text box next to a screenshot.

    py -3.10 tools/make-og-card.py
"""
import os
import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_PDF = os.path.join(ROOT, "downloads", "receipts-sample.pdf")
DEST = os.path.join(ROOT, "assets", "og-card.png")

PAPER = (244, 241, 233)
INK = (26, 24, 21)
MUTED = (109, 102, 86)
LINE = (200, 191, 171)
STAMP = (168, 60, 38)

W, H = 1200, 630
SS = 2  # supersample, then downscale

F = "C:/Windows/Fonts/"
stamp = ImageFont.truetype(F + "segoeuib.ttf", 15 * SS)
head = ImageFont.truetype(F + "georgiab.ttf", 44 * SS)
sans = ImageFont.truetype(F + "segoeui.ttf", 17 * SS)

card = Image.new("RGB", (W * SS, H * SS), PAPER)
d = ImageDraw.Draw(card)

M = 56
d.text((M * SS, 54 * SS), "R E C E I P T S T A C K", font=stamp, fill=STAMP)
d.text((M * SS, 88 * SS), "Turn receipt photos into one dated, indexed PDF.",
       font=head, fill=INK)
d.text((M * SS, 152 * SS), "No upload  \u00b7  no account  \u00b7  no server  \u00b7  free for up to 5 receipts",
       font=sans, fill=MUTED)
d.rectangle([M * SS, 190 * SS - 2, (W - M) * SS, 190 * SS], fill=LINE)

# a real cover page, cropped to just the title + index + total band
doc = pymupdf.open(SRC_PDF)
pix = doc[0].get_pixmap(dpi=220)
page = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
page = page.crop((0, int(page.height * 0.060), page.width, int(page.height * 0.352)))

box_w = (W - 2 * M) * SS
box_h = int(box_w * page.height / page.width)
page = page.resize((box_w, box_h), Image.LANCZOS)
top = 188 * SS
d.rectangle([M * SS - 2, top - 2, M * SS + box_w + 2, top + box_h + 2], fill=LINE)
card.paste(page, (M * SS, top))
d.text((M * SS, [(top + box_h) // SS + 14][0] * SS),
       "the index page, then one receipt per page, in date order",
       font=ImageFont.truetype(F + "segoeui.ttf", 13 * SS), fill=MUTED)

out = card.resize((W, H), Image.LANCZOS)
out.save(DEST, optimize=True)
print("wrote", DEST, os.path.getsize(DEST), "bytes", out.size)
