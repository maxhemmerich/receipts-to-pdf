"""Check a PDF this project produced: page count, text per page, and PNG renders.

Used by ADMIRAL 5 to verify the tool's real output instead of trusting a screenshot.
    py -3.10 tools/check-pdf.py downloads/receipts-sample.pdf --render out/
"""
import argparse, os, sys
import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--render", default="")
    ap.add_argument("--dpi", type=int, default=100)
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    print("file      :", a.pdf)
    print("bytes     :", os.path.getsize(a.pdf))
    print("pages     :", doc.page_count)
    print("metadata  :", {k: v for k, v in doc.metadata.items() if v})
    print()

    for i, page in enumerate(doc):
        w, h = page.rect.width, page.rect.height
        imgs = len(page.get_images(full=True))
        text = page.get_text().strip().replace("\n", " | ")
        print("page %d  %.0fx%.0f  images=%d" % (i + 1, w, h, imgs))
        print("   ", text[:600] if text else "(no text)")
        if a.render:
            os.makedirs(a.render, exist_ok=True)
            pix = page.get_pixmap(dpi=a.dpi)
            out = os.path.join(a.render, "page-%02d.png" % (i + 1))
            pix.save(out)
    if a.render:
        print("\nrendered to", a.render)


if __name__ == "__main__":
    main()
