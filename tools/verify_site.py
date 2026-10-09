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

# The guide pages that carry the tool's search intents. index.html is the tool
# itself. Every one of these must be in sitemap.xml and must link the phone page.
GUIDES = [
    "combine-receipt-photos-into-one-pdf.html",
    "how-to-organize-receipts-for-taxes.html",
    "reimbursement-claim-pdf.html",
    "expense-report-with-receipts.html",
    "multiple-receipts-one-page-pdf.html",
    "scan-receipts-to-pdf-on-a-phone.html",
]
NEW_PAGE = "scan-receipts-to-pdf-on-a-phone.html"
# The cited guide: answers "how long do I have to keep receipts?" by quoting the CRA. It must name
# each source URL and print the sentences verbatim, so a rewrite cannot quietly drop or alter a quote.
CRA_PAGE = "how-long-to-keep-receipts.html"
CRA_SOURCES = [
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/long-should-you-keep-your-income-tax-records.html",
    "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/where-keep-your-records-long-request-permission-destroy-them-early.html",
    "https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/rc188/keeping-records.html",
]
CRA_RULE = ("Keep your records for six years from the end of the last tax year they relate to, "
            "unless you have permission from the CRA to destroy them earlier.")
CRA_RULE_IND = "Keep your tax documents and records for at least six years."
# The second cited guide: the identical retention question for the United States, quoting the IRS.
# Same guard -- its one source URL must be named and its sentences carried verbatim, so a rewrite
# cannot drop or soften a quotation.
IRS_PAGE = "how-long-to-keep-records-irs.html"
IRS_SOURCES = [
    "https://www.irs.gov/businesses/small-businesses-self-employed/how-long-should-i-keep-records",
]
IRS_RULE = ("Generally, you must keep your records that support an item of income, deduction or credit "
            "shown on your tax return until the period of limitations for that tax return runs out.")
IRS_RULE_2 = "Keep records for 3 years if situations (4), (5), and (6) below do not apply to you."


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


def _html_files():
    return ["index.html"] + GUIDES + [CRA_PAGE, IRS_PAGE]


def _loc_for(page):
    return SITE + "/" if page == "index.html" else "%s/%s" % (SITE, page)


def check_new_page_indexable():
    """The phone guide must own its title / description / canonical / OG card."""
    p = os.path.join(ROOT, NEW_PAGE)
    print("check: phone guide is indexable and self-canonical (%s)" % NEW_PAGE)
    if not os.path.exists(p):
        return ["%s is missing" % NEW_PAGE]
    html = open(p, encoding="utf-8").read()
    url = "%s/%s" % (SITE, NEW_PAGE)
    rules = [
        ("title", r"<title>[^<]*scan receipts to one PDF on a phone[^<]*</title>"),
        ("description", r'<meta name="description" content="[^"]{80,}"'),
        ("canonical", re.escape('<link rel="canonical" href="%s">' % url)),
        ("og:url", re.escape('<meta property="og:url" content="%s">' % url)),
        ("og:image", re.escape('<meta property="og:image" content="%s/assets/og-card.png">' % SITE)),
        ("twitter:card", r'<meta name="twitter:card" content="summary_large_image">'),
        ("links the tool", r'href="\./(?:#tool)?"'),
    ]
    failures = []
    for name, pat in rules:
        ok = re.search(pat, html, re.I) is not None
        print("  %-14s : %s" % (name, ok))
        if not ok:
            failures.append("%s: %s is missing or wrong" % (NEW_PAGE, name))
    return failures


def check_new_page_linked():
    """The phone guide must be reachable: from the landing page and a sibling guide."""
    failures = []
    print("check: phone guide is linked into the mesh")
    landing = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    from_landing = NEW_PAGE in landing
    print("  linked from index.html  : %s" % from_landing)
    if not from_landing:
        failures.append("index.html does not link %s" % NEW_PAGE)
    siblings = [
        g for g in GUIDES
        if g != NEW_PAGE and NEW_PAGE in open(os.path.join(ROOT, g), encoding="utf-8").read()
    ]
    print("  linked from guides      : %d/%d" % (len(siblings), len(GUIDES) - 1))
    if not siblings:
        failures.append("no sibling guide links %s" % NEW_PAGE)
    return failures


def check_sitemap_covers_pages():
    """sitemap.xml must list every indexable page and point only at files that exist."""
    failures = []
    html = open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read()
    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", html)
    print("check: sitemap.xml covers every indexable page (%d <loc>)" % len(locs))
    for page in _html_files():
        ok = _loc_for(page) in locs
        print("  %-46s : %s" % (page, ok))
        if not ok:
            failures.append("sitemap.xml does not list %s" % page)
    for loc in locs:
        if not loc.startswith(SITE + "/"):
            failures.append("sitemap.xml lists a URL outside this site: %s" % loc)
            continue
        rel = loc[len(SITE) + 1:] or "index.html"
        if not os.path.exists(os.path.join(ROOT, rel)):
            failures.append("sitemap.xml lists %s, which is not in the tree" % rel)
    return failures


def check_no_external_subresources():
    """No page may load a script/style/image from a non-'self' origin.

    This is the machine check behind the copy's promise: the tool ships
    connect-src 'none' and loads nothing from anywhere else. The GitHub source
    link is an <a href>, not a subresource, so it is correctly not counted.
    """
    failures = []
    print("check: no external subresources on any page")
    pat = re.compile(
        r'<(?:script|img|iframe|source)\b[^>]*\bsrc="([^"]+)"'
        r'|<link\b[^>]*\brel="stylesheet"[^>]*\bhref="([^"]+)"',
        re.I,
    )
    for page in _html_files():
        html = open(os.path.join(ROOT, page), encoding="utf-8").read()
        bad = [m.group(1) or m.group(2) for m in pat.finditer(html)
               if re.match(r"(?:https?:)?//", m.group(1) or m.group(2))]
        print("  %-46s : %s" % (page, "clean" if not bad else "EXTERNAL " + ", ".join(bad)))
        if bad:
            failures.append("%s loads an external subresource: %s" % (page, ", ".join(bad)))
    return failures


def check_og_card():
    """Every page must reference the social card, and the card must be 1200x630."""
    import struct

    print("check: social card (assets/og-card.png)")
    card = os.path.join(ROOT, "assets", "og-card.png")
    if not os.path.exists(card):
        return ["assets/og-card.png is missing"]
    w, h = struct.unpack(">II", open(card, "rb").read(24)[16:24])
    print("  card size               : %dx%d" % (w, h))
    failures = []
    if (w, h) != (1200, 630):
        failures.append("assets/og-card.png is %dx%d, not 1200x630" % (w, h))
    for page in _html_files():
        html = open(os.path.join(ROOT, page), encoding="utf-8").read()
        has_img = ('<meta property="og:image" content="%s/assets/og-card.png">' % SITE) in html
        has_tw = '<meta name="twitter:card" content="summary_large_image">' in html
        ok = has_img and has_tw
        print("  %-46s : %s" % (page, ok))
        if not ok:
            failures.append("%s: missing og:image=%s/assets/og-card.png or twitter:card=summary_large_image"
                            % (page, SITE))
    return failures


def check_served_new_page(fetch):
    """The served phone guide must be byte-identical to the tree copy being shipped."""
    failures = []
    raw = fetch(NEW_PAGE)
    local = open(os.path.join(ROOT, NEW_PAGE), "rb").read()
    print("check: served phone guide == tree")
    if raw is None:
        failures.append("could not fetch the served %s" % NEW_PAGE)
    elif raw != local:
        failures.append("served %s differs from the tree copy (served %d, tree %d bytes)"
                        % (NEW_PAGE, len(raw), len(local)))
    else:
        print("  served == tree : True (%d bytes)" % len(local))
    return failures


def _cited_page_failures(page, title_pat, sources, sentences):
    """A cited guide: indexable, self-canonical, every source named, every sentence quoted verbatim.

    This guards the one thing that made such a page honest -- that its quotations come from the named
    government pages, with the date they were read printed beside them, and that its own price/cap
    figures still match config.js and assets/app.js. Shared by the CRA and IRS guides.
    """
    failures = []
    p = os.path.join(ROOT, page)
    print("check: cited guide is indexable and carries its sources (%s)" % page)
    if not os.path.exists(p):
        return ["%s is missing" % page]
    html = open(p, encoding="utf-8").read()
    url = "%s/%s" % (SITE, page)
    rules = [
        ("title", title_pat),
        ("description", r'<meta name="description" content="[^"]{80,}"'),
        ("canonical", re.escape('<link rel="canonical" href="%s">' % url)),
        ("og:url", re.escape('<meta property="og:url" content="%s">' % url)),
        ("og:image", re.escape('<meta property="og:image" content="%s/assets/og-card.png">' % SITE)),
        ("twitter:card", r'<meta name="twitter:card" content="summary_large_image">'),
        ("links the tool", r'href="\./(?:#tool)?"'),
    ]
    for name, pat in rules:
        ok = re.search(pat, html, re.I) is not None
        print("  %-14s : %s" % (name, ok))
        if not ok:
            failures.append("%s: %s is missing or wrong" % (page, name))

    for src in sources:
        ok = src in html
        print("  source         : %s %s" % ("ok " if ok else "MISSING", src[:64]))
        if not ok:
            failures.append("%s does not name the source %s" % (page, src))
    for sentence in sentences:
        ok = sentence in html
        print("  quote          : %s %s" % ("ok " if ok else "MISSING", sentence[:56]))
        if not ok:
            failures.append("%s does not quote verbatim: %s" % (page, sentence[:56]))
    readstamp = re.search(r"Read \d{4}-\d{2}-\d{2}", html) is not None
    print("  read date      : %s" % readstamp)
    if not readstamp:
        failures.append("%s: no 'Read YYYY-MM-DD' date stamp beside the quotes" % page)

    # the page's own price and free cap must not drift from config.js / assets/app.js
    cfg = open(os.path.join(ROOT, "config.js"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "assets", "app.js"), encoding="utf-8").read()
    pm = re.search(r"PRICE_USD\s*=\s*(\d+)", cfg)
    cm = re.search(r"FREE_LIMIT\s*=\s*(\d+)", js)
    price_ok = bool(pm and ("$%s" % pm.group(1)) in html)
    cap_ok = bool(cm and ("up to %s receipts" % cm.group(1)) in html)
    print("  price $%s      : %s" % (pm.group(1) if pm else "?", price_ok))
    print("  free cap %s     : %s" % (cm.group(1) if cm else "?", cap_ok))
    if not price_ok:
        failures.append("%s: the $%s price (config.js PRICE_USD) is not printed on the page"
                        % (page, pm.group(1) if pm else "?"))
    if not cap_ok:
        failures.append("%s: the free cap %s (app.js FREE_LIMIT) is not stated on the page"
                        % (page, cm.group(1) if cm else "?"))

    # reachable: linked from the landing page and from a sibling guide
    landing = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    from_landing = page in landing
    siblings = [g for g in GUIDES
                if page in open(os.path.join(ROOT, g), encoding="utf-8").read()]
    print("  linked from landing : %s" % from_landing)
    print("  linked from guides  : %d/%d" % (len(siblings), len(GUIDES)))
    if not from_landing:
        failures.append("index.html does not link %s" % page)
    if not siblings:
        failures.append("no sibling guide links %s" % page)
    return failures


def check_cited_page():
    """The CRA guide -- the retention question for Canada."""
    return _cited_page_failures(
        CRA_PAGE,
        r"<title>[^<]*how long do i have to keep receipts[^<]*</title>",
        CRA_SOURCES, (CRA_RULE, CRA_RULE_IND))


def check_cited_page_irs():
    """The IRS guide -- the identical retention question for the United States."""
    return _cited_page_failures(
        IRS_PAGE,
        r"<title>[^<]*how long should i keep records[^<]*</title>",
        IRS_SOURCES, (IRS_RULE, IRS_RULE_2))


def check_served_page(fetch, page):
    """The served copy of `page` must be byte-identical to the tree copy being shipped."""
    failures = []
    raw = fetch(page)
    local = open(os.path.join(ROOT, page), "rb").read()
    print("check: served %s == tree" % page)
    if raw is None:
        failures.append("could not fetch the served %s" % page)
    elif raw != local:
        failures.append("served %s differs from the tree copy (served %d, tree %d bytes)"
                        % (page, len(raw), len(local)))
    else:
        print("  served == tree : True (%d bytes)" % len(local))
    return failures


def _load_generator():
    """Import tools/make-keep-receipts-page.py (hyphenated name -> importlib) to reuse its fetch/plain.

    Reusing the generator's own functions is the point: the live re-assert below must test the source
    pages with exactly the fetch and the text-normalizer that produced the shipped quotes.
    """
    import importlib.util

    path = os.path.join(ROOT, "tools", "make-keep-receipts-page.py")
    spec = importlib.util.spec_from_file_location("make_keep_receipts_page", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not load the generator at %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_cited_sources_live():
    """--served: re-fetch each named government page and re-assert every quoted sentence is still there.

    The shipped page is frozen text; each quote was proven present on its source at build time. This
    re-fetches the source pages on demand, with the generator's own fetch()+plain(), so the suite
    catches a CRA or IRS edit rather than relying on someone re-running the generator. Behind --served
    because it is a network check.
    """
    failures = []
    print("check: cited sources are still live (CRA + IRS)")
    try:
        gen = _load_generator()
    except Exception as e:  # noqa
        return ["could not load the generator for the live source check: %s" % e]

    for label, attr in (("CRA", "SOURCES"), ("IRS", "IRS_SOURCES")):
        sources = getattr(gen, attr, None)
        if not sources:
            failures.append("the generator exposes no %s to re-check" % attr)
            continue
        for key, src in sources.items():
            try:
                code, raw = gen.fetch(src["url"])
            except SystemExit as e:  # fetch() exits if curl is missing
                failures.append("%s %s: fetch aborted: %s" % (label, key, e))
                continue
            print("  %-4s %-4s HTTP %s" % (label, key, code))
            if code != 200 or not raw:
                failures.append("%s %s: the source page %s is no longer readable (HTTP %s)"
                                % (label, key, src["url"], code))
                continue
            text = gen.plain(raw)
            missing = [s for s in src["sentences"] if gen.plain(s) not in text]
            print("    %d/%d quoted sentences still present"
                  % (len(src["sentences"]) - len(missing), len(src["sentences"])))
            for s in missing:
                failures.append("%s %s: the quoted sentence is no longer on %s: %r"
                                % (label, key, src["url"], s[:70]))
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--served", action="store_true", help="also fetch the live site and compare")
    ap.add_argument("--page", default=os.path.join(ROOT, "index.html"),
                    help="index.html to read labels from (default: the tree copy)")
    a = ap.parse_args()

    failures = []
    failures += check_sample_labels(a.page, ROOT, served=False)
    failures += check_new_page_indexable()
    failures += check_new_page_linked()
    failures += check_cited_page()
    failures += check_cited_page_irs()
    failures += check_sitemap_covers_pages()
    failures += check_no_external_subresources()
    failures += check_og_card()
    if a.served:
        fetch = make_fetcher()
        failures += check_served_page_matches_tree(a.page, fetch)
        failures += check_served_new_page(fetch)
        failures += check_served_page(fetch, CRA_PAGE)
        failures += check_served_page(fetch, IRS_PAGE)
        failures += check_sample_labels(a.page, ROOT, served=True, fetch=fetch)
        failures += check_cited_sources_live()
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
