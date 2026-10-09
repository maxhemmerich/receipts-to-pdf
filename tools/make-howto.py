"""Builds downloads/how-to-use.pdf — the one-page sheet that ships with the tool.
    py -3.10 tools/make-howto.py
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, ListFlowable,
                                ListItem, HRFlowable, KeepTogether)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "..", "downloads", "how-to-use.pdf")

# The price and the address are read from the site's own build outputs, so this sheet cannot
# drift from what the page states: PRICE_USD out of config.js, the landing URL out of
# sitemap.xml (the same source tools/indexnow.py uses).
import re
def _one(pattern, text, what):
    m = re.search(pattern, text)
    if not m:
        raise SystemExit("make-howto.py: could not read %s from the site (pattern %r)"
                         % (what, pattern))
    return m.group(1)

_cfg = open(os.path.join(ROOT, "config.js"), encoding="utf-8").read()
PRICE = _one(r"PRICE_USD\s*=\s*(\d+)", _cfg, "PRICE_USD from config.js")
_sm = open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read()
SITE = _one(r"<loc>\s*([^<]+?)\s*</loc>", _sm, "the landing URL from sitemap.xml")
SITE_PRETTY = re.sub(r"^https?://", "", SITE).rstrip("/")

INK = colors.HexColor("#1a1815")
MUTED = colors.HexColor("#5d5748")

title = ParagraphStyle("title", fontName="Times-Bold", fontSize=20, leading=23, textColor=INK, spaceAfter=2)
sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=10)
h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=INK,
                    spaceBefore=11, spaceAfter=4)
body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.4, leading=12.6, textColor=INK)
step = ParagraphStyle("step", parent=body, spaceAfter=3.5)
bullet = ParagraphStyle("bullet", parent=body, spaceAfter=2.5)
foot = ParagraphStyle("foot", fontName="Helvetica", fontSize=8.6, leading=11.4,
                      textColor=MUTED, spaceBefore=9)


def numbered(items):
    return ListFlowable(
        [ListItem(Paragraph(t, step), leftIndent=16) for t in items],
        bulletType="1", bulletFontName="Helvetica-Bold", bulletFontSize=9.4,
        leftIndent=14, bulletDedent=14, spaceBefore=0, spaceAfter=0)


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(t, bullet), leftIndent=14) for t in items],
        bulletType="bullet", bulletChar="-", bulletFontName="Helvetica",
        leftIndent=13, bulletDedent=13, spaceBefore=0, spaceAfter=0)


def rule():
    return HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#c8bfab"),
                      spaceBefore=6, spaceAfter=2)


story = [
    Paragraph("Combine receipt photos into one PDF", title),
    Paragraph("ReceiptStack &mdash; receipt photos in, one dated indexed PDF out. Everything runs in "
              "your own browser.", sub),
    rule(),
    Paragraph("The seven steps", h2),
    numbered([
        "Open the page. Nothing to install and no account is needed.",
        "Photograph each paper receipt. One photo per receipt. Straight on, in good light.",
        "Drag the photos onto the drop zone, or click &ldquo;choose files&rdquo; and pick them.",
        "Check the list. The date fills itself in when the date is in the filename. If a row says "
        "&ldquo;no date in the filename&rdquo;, type the date in. Add a short note and the amount.",
        "Use the up and down arrows to set the order. The circular arrow turns a photo 90 degrees.",
        "Type a name for the PDF, choose Letter or A4, then press &ldquo;Build the PDF&rdquo;.",
        "Press the download button. The file goes to your Downloads folder.",
    ]),
    Paragraph("What is in the PDF", h2),
    bullets([
        "Page 1 is an index: every receipt in date order, with its amount and a total for the batch.",
        "Then one receipt per page, the whole photo, nothing cropped.",
        "A footer on every page tells you which receipt it is, its date and its amount, so the "
        "pages still make sense once they are printed and shuffled.",
        "Photos are resized to 2200 pixels on the long edge, which keeps a year of receipts a few "
        "megabytes and small enough to email.",
    ]),
    Paragraph("Your photos never leave your machine", h2),
    Paragraph(
        "There is no upload and there is no server behind the page that could receive your files. "
        "The page ships a content-security policy that blocks every network request, so it cannot "
        "send your pictures anywhere even if something tried to. The PDF is assembled by the "
        "JavaScript already running in your browser tab. If you are handing it a year of receipts, "
        "open the page source and read that line for yourself.", body),
    Paragraph("Free and unlocked", h2),
    Paragraph(
        "The free version puts up to 5 receipts in one PDF. The unlocked version has no limit and "
        "drops the small footer mark, for $%s once. Both produce the same kind of file, and neither "
        "one uploads anything." % PRICE, body),
    Paragraph("One thing it does not do", h2),
    Paragraph(
        "ReceiptStack is not tax advice and it does not read the numbers off your receipts for "
        "you. It puts your receipts into one file, in order, with a total. What you claim is your "
        "call and your accountant&rsquo;s.", body),
    rule(),
    Paragraph(
        'ReceiptStack &mdash; <link href="%s">%s</link>. Free for up to 5 receipts per PDF; '
        '$%s once removes the limit and the footer mark.' % (SITE, SITE_PRETTY, PRICE), foot),
]

doc = SimpleDocTemplate(OUT, pagesize=letter,
                        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.62 * inch, bottomMargin=0.55 * inch,
                        title="Combine receipt photos into one PDF - ReceiptStack",
                        author="ReceiptStack", subject="Combine receipt photos into one PDF")
doc.build(story)
print("wrote", os.path.abspath(OUT), os.path.getsize(OUT), "bytes")
