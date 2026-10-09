#!/usr/bin/env python
# make-keep-receipts-page.py -- build how-long-to-keep-receipts.html from the CRA's own pages.
#
# WHY THIS IS A BUILD TOOL, NOT A HAND-WRITTEN PAGE
# The new guide answers "how long do I have to keep receipts?" The only honest way to do that is to
# quote the rule from the Canada Revenue Agency, name the page it came from, and print the date it was
# read. This script FETCHES the CRA pages, proves each quoted sentence is actually present in the page
# it is attributed to, stamps the read date, and only then writes the HTML. If CRA cannot be read, or a
# sentence is not found where it is claimed to be, it ABORTS and writes nothing -- so the page's quotes
# can never be carried from memory, and a re-run after CRA edits a page cannot silently publish a stale
# quote (the sentence check fails and the build stops).
#
# It is a BUILD-TIME fetch: the page itself loads nothing from CRA. The page carries the CRA URL as
# text and as an <a href> (a link, not a subresource), so the site's own promise -- connect-src 'none'
# and no external subresource anywhere -- is untouched.
#
#   py -3.10 tools/make-keep-receipts-page.py           # fetch, verify, write the page
#   py -3.10 tools/make-keep-receipts-page.py --check   # fetch + verify only, write nothing
#
# Fetching is done with curl (the box's curl reaches canada.ca; Python's own http client times out on
# it). If curl is missing the script aborts rather than falling back to a remembered quote.
import argparse
import html
import os
import re
import subprocess
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "how-long-to-keep-receipts.html")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReceiptStack-build-check"

# The three named CRA pages this track quotes. `title` is the page's own heading; `sentences` are the
# ones this build is allowed to print, each asserted to be present in the fetched text.
SOURCES = {
    "ind": {
        "url": "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/long-should-you-keep-your-income-tax-records.html",
        "title": "How long should you keep your income tax records?",
        "sentences": [
            "Keep your tax documents and records for at least six years.",
            "The CRA may ask to see these documents later to support your claims.",
            "You may need to show more than just official receipts.",
            "Keep cancelled cheques, bank statements, and any other proof for deductions or credits you claimed.",
            "You should also keep a copy of your tax return and any notices of assessment or reassessment.",
        ],
    },
    "biz": {
        "url": "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/where-keep-your-records-long-request-permission-destroy-them-early.html",
        "title": "Where to keep your records, for how long and how to request the permission to destroy them early",
        "sentences": [
            "Generally, you must keep all required records and supporting documents for a period of six years from the end of the last tax year they relate to.",
            "If you file an income tax return late, you must keep your records for six years from the date you file that return.",
        ],
    },
    "rc188": {
        "url": "https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/rc188/keeping-records.html",
        "title": "Keeping Records (RC188)",
        "sentences": [
            "Keep your records for six years from the end of the last tax year they relate to, unless you have permission from the CRA to destroy them earlier.",
            "You may need to keep some source documents to provide details that support your records.",
        ],
    },
}


# The page template. The quote text is NEVER written here -- only [[TOKEN]] placeholders that main()
# fills from the live CRA fetch, so a quote cannot be carried from memory.
TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<title>How long do I have to keep receipts? &mdash; the CRA&rsquo;s six-year rule | ReceiptStack</title>
<meta name="description" content="The Canada Revenue Agency&rsquo;s own rule, quoted from canada.ca: generally keep your records for six years from the end of the last tax year they relate to. This page prints the source URL and the date it was read beside each quote.">
<link rel="canonical" href="https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-receipts.html">
<meta name="theme-color" content="#f4f1e9">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ReceiptStack">
<meta property="og:title" content="How long do I have to keep receipts? &mdash; the CRA&rsquo;s six-year rule">
<meta property="og:description" content="Quoted from canada.ca, with the source URL and the date it was read: generally, keep your records for six years from the end of the last tax year they relate to. No upload, no account.">
<meta property="og:url" content="https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-receipts.html">
<meta property="og:image" content="https://maxhemmerich.github.io/receipts-to-pdf/assets/og-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The ReceiptStack index page: seven receipts listed with dates and amounts, total $712.14">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="How long do I have to keep receipts? &mdash; the CRA&rsquo;s six-year rule">
<meta name="twitter:description" content="The CRA&rsquo;s own rule, quoted from canada.ca with the source URL and the date it was read.">
<meta name="twitter:image" content="https://maxhemmerich.github.io/receipts-to-pdf/assets/og-card.png">
<link rel="stylesheet" href="assets/style.css">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication",
      "@id": "https://maxhemmerich.github.io/receipts-to-pdf/#app",
      "name": "ReceiptStack",
      "url": "https://maxhemmerich.github.io/receipts-to-pdf/",
      "description": "Turns photos of paper receipts into one dated, indexed PDF: a cover index in date order with a total, then one receipt per page. Runs entirely in the browser - no upload, no account, no server.",
      "applicationCategory": "BusinessApplication",
      "operatingSystem": "Any device with a modern web browser",
      "featureList": [
        "One receipt per page, nothing cropped",
        "Cover index in date order with a total for the whole batch",
        "Dates read from the filename when they are in there",
        "Your photos never leave your browser"
      ]
    },
    {
      "@type": "FAQPage",
      "@id": "https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-receipts.html#faq",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "How long do I have to keep receipts in Canada?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "The Canada Revenue Agency's rule, quoted on this page from its own canada.ca pages, is generally six years, counted from the end of the last tax year the records relate to. The source URL and the date it was read are printed beside each quote."
          }
        },
        {
          "@type": "Question",
          "name": "When does the six-year period start?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "In the CRA's wording, six years from the end of the last tax year the records relate to, not from the day of the purchase. This page quotes the rule; it does not compute your own period."
          }
        },
        {
          "@type": "Question",
          "name": "What if I filed my return late?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "The CRA says if you file an income tax return late, you must keep your records for six years from the date you file that return. That sentence is quoted, with its source, further down this page."
          }
        },
        {
          "@type": "Question",
          "name": "Does ReceiptStack tell me what to keep or for how long?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "No. The retention rule is the CRA's and is quoted here from its pages. ReceiptStack only assembles the receipts you give it into one dated, indexed PDF, in your browser - nothing is uploaded, there is no account, and it makes no tax decisions."
          }
        },
        {
          "@type": "Question",
          "name": "How many receipts can I put in one PDF?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Free for a PDF of up to 5 receipts, index and totals included, with no account and no email. Above that, a one-time $9 unlock removes the limit and the small footer mark."
          }
        }
      ]
    }
  ]
}
</script>
</head>
<body>

<header class="bar">
  <span class="brand">ReceiptStack</span>
  <nav>
    <a href="./">The tool</a>
    <a href="./#sample">Sample output</a>
    <a href="./#privacy">Privacy</a>
  </nav>
</header>

<main>

  <p class="eyebrow">Guide</p>
  <h1>How long do I have to keep receipts?</h1>
  <p class="lede">The answer is a rule the Canada Revenue Agency publishes itself, and it is short:
  <b>generally six years</b>. This page quotes the rule from the CRA&rsquo;s own pages, prints the source
  URL and the date it was read beside every quote, and is plain about the small part the rest of this
  site plays &mdash; turning a pile of receipt photos into one dated, indexed file, in your browser, with
  nothing uploaded.</p>
  <p><a href="./#tool">Open the tool</a> &middot; <a href="downloads/receipts-sample.pdf">see a real
  output first</a> &middot; <a href="how-to-organize-receipts-for-taxes.html">how to organize receipts
  for taxes</a> &middot; <a href="combine-receipt-photos-into-one-pdf.html">combine receipt photos into
  one PDF</a> &middot; <a href="reimbursement-claim-pdf.html">for a reimbursement claim</a> &middot;
  <a href="expense-report-with-receipts.html">for an expense report</a> &middot;
  <a href="multiple-receipts-one-page-pdf.html">multiple receipts in one PDF</a> &middot;
  <a href="scan-receipts-to-pdf-on-a-phone.html">from a phone</a></p>

  <section class="block">
    <h2>The short answer: six years</h2>
    <p>For an individual filing an income tax return, the CRA&rsquo;s instruction is one sentence:</p>
    <blockquote cite="https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/long-should-you-keep-your-income-tax-records.html">[[Q_IND_1]]</blockquote>
    [[CITE_IND]]
    <p>For a business, and for the general rule, the same period is stated against a defined starting
    point rather than a fixed date &mdash; the end of the last tax year the records relate to:</p>
    <blockquote cite="https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/rc188/keeping-records.html">[[Q_RC188_1]]</blockquote>
    [[CITE_RC188]]
  </section>

  <section class="block">
    <h2>In the CRA&rsquo;s own words</h2>
    <p>Nothing on this page is the site&rsquo;s own reading of the tax law. The rule above is a direct
    quotation, and so is the longer statement of it from the CRA&rsquo;s records page for businesses:</p>
    <blockquote cite="https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/where-keep-your-records-long-request-permission-destroy-them-early.html">[[Q_BIZ_1]]</blockquote>
    [[CITE_BIZ]]
    <p>Read the wording closely, because the clock is not the day of the purchase. The six years run
    from the end of the last tax year the records relate to &mdash; as the CRA puts it, in the same
    passage, where it also defines the tax year as the fiscal period for corporations and the calendar
    year for individuals. If that timing matters to you, follow the links above rather than take a
    summary from a tool page.</p>
  </section>

  <section class="block">
    <h2>The details the same CRA pages give</h2>
    <p>Three more sentences from those pages answer the questions people ask next. Each one is quoted
    with the page it came from.</p>
    <dl class="facts">
      <dt>Filed late?</dt>
      <dd>[[BIZ_SENT_2]] <span class="dim">&mdash; CRA, <i>Where to keep your records</i>.</span></dd>
      <dt>Do I keep more than the receipts themselves?</dt>
      <dd>[[IND_SENT_4]] <span class="dim">&mdash; CRA, <i>How long should you keep your income tax
      records?</i></span></dd>
      <dt>And the return itself?</dt>
      <dd>[[IND_SENT_5]] <span class="dim">&mdash; same CRA page.</span></dd>
      <dt>Why keep them at all?</dt>
      <dd>[[IND_SENT_2]] <span class="dim">&mdash; same CRA page.</span></dd>
      <dt>Receipts as well as the summary records?</dt>
      <dd>[[RC188_SENT_2]] <span class="dim">&mdash; CRA, <i>Keeping Records (RC188)</i>.</span></dd>
    </dl>
    <p class="dim">One of those sentences is easy to skip over: [[IND_SENT_3]] &mdash; the CRA does not
    promise that a receipt on its own is enough if a claim is questioned, which is the reason to keep
    the return, the notices and the statements together with the receipts, not just the receipts.</p>
  </section>

  <section class="block">
    <h2>What this page is not</h2>
    <p>This is a quotation of a published rule, not tax advice. It does not know your situation &mdash;
    whether you are an individual, a corporation, a trust or a charity, whether your records are for
    income tax or for GST/HST, or whether the CRA has told you to keep something longer. Where the rule
    is not the whole answer for you, the pages linked here are the source, and your accountant is the
    person to ask.</p>
    <p>The tool on the rest of this site makes no tax claim at all. It does not decide what you can
    claim, does not compute a deduction, and does not track any retention period for you. It builds a
    PDF.</p>
  </section>

  <section class="block">
    <h2>Making receipts you can keep for six years</h2>
    <p>The rule says keep the records. Paper makes that hard: a thermal till receipt left in a drawer
    or a car can fade to unreadable inside a year, well before the six are up. A photograph taken the
    day you get the receipt is the copy that survives the wait &mdash; and a dated, indexed file of
    those photographs is the copy you can actually lay hands on when you need it.</p>
    <p>That is the one thing this site does. <a href="./#tool">ReceiptStack</a> takes the receipt photos
    you drop in and assembles them into one PDF: a cover index that lists every receipt in date order
    with its amount and a total, then one receipt per page with its date and amount in the footer. It
    runs entirely in the browser tab &mdash; there is no upload, no server, no account, enforced by a
    content-security policy whose <span class="dim">connect-src 'none'</span> directive blocks every
    network request. It is free for a PDF of up to <b>5 receipts</b>; a one-time <b>$9</b> unlock
    removes the cap and the small footer mark. It does not read the receipt, does not OCR it and does
    not guess an amount &mdash; the photo is the record, and every number but a date in the filename is
    one you type.</p>
  </section>

  <section class="block">
    <h2>Questions</h2>
    <dl class="facts">
      <dt>How long do I have to keep receipts in Canada?</dt>
      <dd>The CRA&rsquo;s rule, quoted above from its own pages, is generally six years &mdash; counted
      from the end of the last tax year the records relate to. The CRA&rsquo;s own page for individuals
      states it as: <i>&ldquo;[[Q_IND_LEDE]]&rdquo;</i></dd>
      <dt>When does the six-year period start?</dt>
      <dd>In the CRA&rsquo;s wording, six years from the end of the last tax year the records relate to
      &mdash; not from the day of the purchase. This page quotes the rule; it does not compute your own
      period.</dd>
      <dt>What if I filed my return late?</dt>
      <dd>[[BIZ_SENT_2]] &mdash; quoted from the CRA&rsquo;s records page, linked above.</dd>
      <dt>Does ReceiptStack tell me what to keep or for how long?</dt>
      <dd>No. The retention rule is the CRA&rsquo;s and is quoted here from its pages. ReceiptStack only
      assembles the receipts you give it into one dated, indexed PDF, in your browser &mdash; nothing is
      uploaded, there is no account, and it makes no tax decisions.</dd>
      <dt>How many receipts can I put in one PDF?</dt>
      <dd>Free for a PDF of up to 5 receipts, index and totals included, with no account and no email.
      Above that, a one-time $9 unlock removes the limit and the small footer mark.</dd>
    </dl>
  </section>

  <section class="block">
    <h2>Sources</h2>
    <p class="dim">Every quotation on this page was read from these Canada Revenue Agency pages on
    [[DATE_READ]] ([[DATE_READ_LONG]]), and the sentence was matched against the page at build time.
    CRA material is reproduced here for reference under Crown copyright.</p>
    <ul class="dim">
      <li>Canada Revenue Agency &mdash; <i>How long should you keep your income tax records?</i><br>
      <a href="https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/long-should-you-keep-your-income-tax-records.html">https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/long-should-you-keep-your-income-tax-records.html</a></li>
      <li>Canada Revenue Agency &mdash; <i>Where to keep your records, for how long and how to request the permission to destroy them early</i><br>
      <a href="https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/where-keep-your-records-long-request-permission-destroy-them-early.html">https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/keeping-records/where-keep-your-records-long-request-permission-destroy-them-early.html</a></li>
      <li>Canada Revenue Agency &mdash; <i>Keeping Records (RC188)</i><br>
      <a href="https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/rc188/keeping-records.html">https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/rc188/keeping-records.html</a></li>
    </ul>
  </section>

  <footer class="foot">
    <p><a href="./">ReceiptStack</a> &mdash; one page, no backend. <a href="https://github.com/maxhemmerich/receipts-to-pdf">Source</a>.</p>
    <p class="dim">Not tax advice. The retention rule above is the CRA&rsquo;s, quoted with its source; this tool puts your receipts in one file and nothing more.</p>
  </footer>

</main>

</body>
</html>
'''


def fetch(url, timeout=60):
    """Return (status_code, body) via curl. (0, None) if the request failed."""
    try:
        p = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", str(timeout), "-A", UA,
             "-w", "\n%{http_code}", url],
            capture_output=True,
        )
    except FileNotFoundError:
        sys.exit("make-keep-receipts-page: curl is required to read the CRA pages; none on PATH.")
    out = p.stdout.decode("utf-8", "replace")
    body, _, code = out.rpartition("\n")
    try:
        return int(code.strip()), body
    except ValueError:
        return 0, body


def plain(raw):
    """Fetched HTML -> whitespace-normalized visible text (punctuation kept exact)."""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([.,;:!?])", r"\1", t)
    return t


def date_modified(raw):
    m = re.search(r'name="dcterms\.modified"[^>]*content="([^"]+)"', raw)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify the quotes, write nothing")
    a = ap.parse_args()

    read = date.today()
    quotes = {}
    meta = {}
    for key, src in SOURCES.items():
        code, raw = fetch(src["url"])
        print("fetch %-6s %s -> HTTP %s" % (key, src["url"], code))
        if code != 200 or not raw:
            sys.exit("ABORT: could not read %s (HTTP %s). No page written; a quote is never "
                     "carried from memory." % (src["url"], code))
        text = plain(raw)
        for s in src["sentences"]:
            if plain(s) not in text:
                sys.exit("ABORT: the sentence %r was not found verbatim on %s. CRA may have changed "
                         "the page -- refusing to publish a quote it can no longer stand behind."
                         % (s[:60], src["url"]))
        quotes[key] = {s: plain(s) for s in src["sentences"]}
        meta[key] = date_modified(raw)
        print("  ok  %d/%d sentences verified verbatim; page last modified %s"
              % (len(src["sentences"]), len(src["sentences"]), meta[key]))

    if a.check:
        print("check only: %s NOT written." % os.path.basename(OUT))
        return

    def cite(key):
        src = SOURCES[key]
        mod = meta[key] or "unknown"
        return ('<p class="cite">Source: Canada Revenue Agency &mdash; <i>%s</i>. '
                '<a href="%s">%s</a><br>Read %s &middot; Canada.ca page last modified %s. '
                'Crown copyright, reproduced for reference.</p>'
                % (html.escape(src["title"]), src["url"], src["url"],
                   read.isoformat(), mod))

    q_ind = quotes["ind"]["Keep your tax documents and records for at least six years."]
    q_rc188 = quotes["rc188"]["Keep your records for six years from the end of the last tax year they relate to, unless you have permission from the CRA to destroy them earlier."]
    q_biz = quotes["biz"]["Generally, you must keep all required records and supporting documents for a period of six years from the end of the last tax year they relate to."]

    read_long = "%d %s %d" % (read.day, read.strftime("%B"), read.year)

    page = (TEMPLATE
            .replace("[[DATE_READ]]", read.isoformat())
            .replace("[[DATE_READ_LONG]]", read_long)
            .replace("[[Q_IND_LEDE]]", html.escape(q_ind))
            .replace("[[Q_IND_1]]", html.escape(q_ind))
            .replace("[[Q_RC188_1]]", html.escape(q_rc188))
            .replace("[[Q_BIZ_1]]", html.escape(q_biz))
            .replace("[[RC188_SENT_2]]", html.escape(quotes["rc188"]["You may need to keep some source documents to provide details that support your records."]))
            .replace("[[BIZ_SENT_2]]", html.escape(quotes["biz"]["If you file an income tax return late, you must keep your records for six years from the date you file that return."]))
            .replace("[[IND_SENT_2]]", html.escape(quotes["ind"]["The CRA may ask to see these documents later to support your claims."]))
            .replace("[[IND_SENT_3]]", html.escape(quotes["ind"]["You may need to show more than just official receipts."]))
            .replace("[[IND_SENT_4]]", html.escape(quotes["ind"]["Keep cancelled cheques, bank statements, and any other proof for deductions or credits you claimed."]))
            .replace("[[IND_SENT_5]]", html.escape(quotes["ind"]["You should also keep a copy of your tax return and any notices of assessment or reassessment."]))
            .replace("[[CITE_IND]]", cite("ind"))
            .replace("[[CITE_BIZ]]", cite("biz"))
            .replace("[[CITE_RC188]]", cite("rc188")))

    assert "[[" not in page, "make-keep-receipts-page: an unsubstituted placeholder remains"
    open(OUT, "w", newline="\n", encoding="utf-8").write(page)
    print("wrote %s (%d bytes), quotes read %s" % (os.path.relpath(OUT, ROOT), len(page.encode("utf-8")), read.isoformat()))


if __name__ == "__main__":
    main()
