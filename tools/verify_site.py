"""verify_site.py — the ReceiptStack check suite.

Run before every ship:

    py -3.10 tools/verify_site.py            # checks the working tree
    py -3.10 tools/verify_site.py --served   # also re-fetches the live site

Exit code 0 = every check passed; 1 = at least one check failed (the failing
check prints the drift). Nothing here writes to the site or the network unless
--served is given.

WHY THIS EXISTS (grok-4.7 critique, 2026-10-08 23:03):
The page names, for each sample PDF, its receipt count, page count, KB figure
and exact byte count. A cold reviewer read "648 KB" beside a 663,142-byte file
and called it a mismatch. Both numbers are the same file under the page's own
humanizer (663,142 / 1024 = 647.6 -> "648 KB"), but the class of bug is real: a
page edit that changes a file, or a number typed by hand beside a rebuilt file,
can silently diverge. This check reads the numbers OUT OF index.html and compares
them to the files, byte for byte, so any drift fails the check instead of a
reviewer finding it.
"""
import argparse
import hashlib
import os
import re
import sys

try:
    import pymupdf
except ImportError:
    sys.exit("verify_site.py: pymupdf is required (py -3.10 -m pip install pymupdf)")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://maxhemmerich.github.io/receipts-to-pdf"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def bytes_human(b):
    """The page's own bytesHuman() from assets/app.js, reproduced exactly.

    JS: (b/1024).toFixed(0) + ' KB' for b < 1 MiB.  toFixed(0) rounds half away
    from zero; Python's format() rounds half to even, so round by hand.
    """
    if b < 1024:
        return "%d B" % b
    if b < 1024 * 1024:
        return "%d KB" % int(b / 1024 + 0.5)
    return "%.1f MB" % (b / 1048576)


def sha8(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:8]


def measure_pdf(path):
    """Return {bytes, pages, receipts, mark_lines, mark_pages} for a PDF."""
    doc = pymupdf.open(path)
    pages = doc.page_count
    receipt_pages = 0
    receipts = 0
    mark_lines = 0
    mark_pages = 0
    for page in doc:
        text = page.get_text()
        m = re.search(r"Receipt\s+(\d+)\s+of\s+(\d+)", text)
        if m:
            receipt_pages += 1
            receipts = max(receipts, int(m.group(2)))
        marks_here = text.count("Made with ReceiptStack")
        mark_lines += marks_here
        if marks_here:
            mark_pages += 1
    doc.close()
    return {
        "bytes": os.path.getsize(path),
        "pages": pages,
        "receipts": receipts,
        "receipt_pages": receipt_pages,
        "mark_lines": mark_lines,
        "mark_pages": mark_pages,
    }


def parse_labels(html):
    """Pull (href, description) for every downloads/*.pdf named in the page."""
    out = []
    pat = re.compile(
        r'<a class="file" href="(downloads/[^"]+\.pdf)">[^<]*</a>\s*'
        r'<span class="dim">(.*?)</span>',
        re.S,
    )
    for m in pat.finditer(html):
        href = m.group(1)
        desc = re.sub(r"\s+", " ", m.group(2)).strip()
        out.append((href, desc))
    return out


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def check_sample_labels(page_path, file_root, served=False, fetch=None):
    """The page's named counts for each sample PDF must match the file itself.

    page_path : path to an index.html to read the labels from
    file_root : directory the 'downloads/...' hrefs are relative to
    (when served=True, fetch is a callable (href) -> bytes for the served copy)
    """
    failures = []
    html = open(page_path, encoding="utf-8").read()
    labels = parse_labels(html)
    if not labels:
        return ["no downloads/*.pdf label blocks found in %s" % page_path]

    printed = []
    for href, desc in labels:
        local = os.path.join(file_root, href)
        if not os.path.exists(local):
            failures.append("%s named on the page but missing at %s" % (href, local))
            continue
        meas = measure_pdf(local)

        got = {
            "receipts": _claim(desc, r"(\d+)\s+receipts?\b"),
            "pages": _claim(desc, r"(\d+)\s+pages?\b"),
            "kb": _claim(desc, r"(\d+)\s+KB\b"),
            "bytes": _claim(desc, r"\(([\d,]+)\s+bytes\)", strip_comma=True),
        }
        want = {
            "receipts": meas["receipts"],
            "pages": meas["pages"],
            "kb": int(bytes_human(meas["bytes"]).split()[0]) if meas["bytes"] >= 1024 else None,
            "bytes": meas["bytes"],
        }

        for key in ("receipts", "pages", "kb", "bytes"):
            if got[key] is None:
                continue  # the page makes no claim of that kind (e.g. how-to-use)
            if got[key] != want[key]:
                failures.append(
                    "%s: page says %s=%s, file measures %s=%s (from %r)"
                    % (href, key, got[key], key, want[key], desc[:80])
                )

        # the mark claim, heart of the grok-4.7 finding #2: if the page says
        # every receipt page carries the mark, it must; "no footer mark" -> 0.
        if re.search(r"footer mark", desc, re.I):
            says_every = bool(re.search(r"every receipt page carries", desc, re.I))
            says_none = bool(re.search(r"\bno footer mark\b", desc, re.I))
            if says_every and meas["mark_pages"] != meas["receipt_pages"]:
                failures.append(
                    "%s: page says the mark is on EVERY receipt page, but "
                    "mark_pages=%d receipt_pages=%d"
                    % (href, meas["mark_pages"], meas["receipt_pages"])
                )
            if says_none and meas["mark_lines"] != 0:
                failures.append(
                    "%s: page says NO footer mark, but found %d mark line(s)"
                    % (href, meas["mark_lines"])
                )

        # served copy must be byte-identical to the one in the tree
        served_note = ""
        if served and fetch is not None:
            raw = fetch(href)
            if raw is None:
                failures.append("%s: fetch failed" % href)
            elif len(raw) != meas["bytes"]:
                failures.append(
                    "%s: served %d bytes, tree %d bytes" % (href, len(raw), meas["bytes"])
                )
            else:
                served_note = " served==tree"

        printed.append(
            "  %-34s bytes=%-8d %-7s pages=%d receipts=%d mark_pages=%d/%d sha=%s%s"
            % (
                href,
                meas["bytes"],
                bytes_human(meas["bytes"]),
                meas["pages"],
                meas["receipts"],
                meas["mark_pages"],
                meas["receipt_pages"],
                sha8(local),
                served_note,
            )
        )

    # the page's claims themselves are internally consistent (each number present)
    print("check: sample-file labels on %s" % ("the served page" if served else page_path))
    for line in printed:
        print(line)
    return failures


def check_config():
    """config.js must keep both constants empty until Max's rail exists (dormant door)."""
    failures = []
    cfg = open(os.path.join(ROOT, "config.js"), encoding="utf-8").read()
    if not re.search(r'CHECKOUT_URL\s*=\s*""', cfg):
        failures.append("config.js: CHECKOUT_URL is not empty — the door is meant to be dormant pre-rail")
    if not re.search(r'UNLOCK_CODE\s*=\s*""', cfg):
        failures.append("config.js: UNLOCK_CODE is not empty — no digest should be committed pre-rail")
    if not re.search(r"PRICE_USD\s*=\s*9\b", cfg):
        failures.append("config.js: PRICE_USD is not 9")
    print("check: config.js constants")
    print("  CHECKOUT_URL='' : %s" % bool(re.search(r'CHECKOUT_URL\s*=\s*""', cfg)))
    print("  UNLOCK_CODE=''  : %s" % bool(re.search(r'UNLOCK_CODE\s*=\s*""', cfg)))
    print("  PRICE_USD=9     : %s" % bool(re.search(r"PRICE_USD\s*=\s*9\b", cfg)))
    return failures


def check_paid_door_atomic():
    """A live buy link must require BOTH halves in assets/app.js."""
    failures = []
    js = open(os.path.join(ROOT, "assets", "app.js"), encoding="utf-8").read()
    ok = re.search(r"haveUrl\s*&&\s*haveCode", js) is not None
    if not ok:
        failures.append(
            "assets/app.js: the live-buy branch is no longer guarded by `haveUrl && haveCode` "
            "— the paid door may no longer be atomic"
        )
    # the code box must be shown exactly when a digest exists
    rowok = re.search(r"row\.hidden\s*=\s*!\s*haveCode", js) is not None
    if not rowok:
        failures.append("assets/app.js: the code box is no longer gated on haveCode")
    print("check: paid door is atomic (assets/app.js)")
    print("  live link needs both halves : %s" % ok)
    print("  code box gated on digest    : %s" % rowok)
    return failures


def _claim(desc, pattern, strip_comma=False):
    m = re.search(pattern, desc)
    if not m:
        return None
    s = m.group(1).replace(",", "") if strip_comma else m.group(1)
    return int(s)


# --------------------------------------------------------------------------- #
# --served fetch
# --------------------------------------------------------------------------- #
def make_fetcher():
    import urllib.request

    def fetch(rel):
        url = "%s/%s" % (SITE, rel)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                if r.status != 200:
                    return None
                return r.read()
        except Exception as e:  # noqa
            print("  fetch error %s: %s" % (url, e))
            return None

    return fetch


def check_served_page_matches_tree(page_path, fetch):
    """The served index.html must be byte-identical to the tree copy being shipped."""
    failures = []
    raw = fetch("index.html")
    local = open(page_path, "rb").read()
    print("check: served page == tree page")
    if raw is None:
        failures.append("could not fetch the served index.html")
    elif raw != local:
        failures.append(
            "served index.html differs from the tree copy (served %d bytes, tree %d bytes)"
            % (len(raw), len(local))
        )
        print("  served bytes : %d" % len(raw))
        print("  tree bytes   : %d" % len(local))
    else:
        print("  served == tree : True (%d bytes)" % len(local))
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--served", action="store_true", help="also fetch the live site and compare")
    ap.add_argument("--page", default=os.path.join(ROOT, "index.html"),
                    help="index.html to read labels from (default: the tree copy)")
    a = ap.parse_args()

    failures = []
    failures += check_sample_labels(a.page, ROOT, served=False)
    if a.served:
        fetch = make_fetcher()
        failures += check_served_page_matches_tree(a.page, fetch)
        failures += check_sample_labels(a.page, ROOT, served=True, fetch=fetch)
    failures += check_config()
    failures += check_paid_door_atomic()

    print()
    if failures:
        print("FAIL — %d problem(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        sys.exit(1)
    print("PASS — every check matched.")


if __name__ == "__main__":
    main()
