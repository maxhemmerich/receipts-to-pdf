# ReceiptStack

Turn a pile of receipt photos into one dated, indexed PDF. For tax filing or getting reimbursed.

Everything happens in the browser tab. There is no backend, no API key, no account and no upload —
enforced by a content-security policy with `connect-src 'none'`, not just by a promise in the copy.

Live: https://maxhemmerich.github.io/receipts-to-pdf/

## What it does

- Drop in JPG/PNG/WebP photos of paper receipts.
- Reads the date out of the filename when it is in there (`IMG_20260305_1420.jpg`, `2026-03-05.jpg`,
  `Scan_20260503-1420.png`). Anything ambiguous is left blank for you to type.
- Add a note and an amount per receipt, reorder with the arrows, rotate 90 degrees if a photo is
  sideways.
- Produces one PDF: page 1 is an index of every receipt in date order with a total, then one receipt
  per page with its date and amount in the footer.
- Letter or A4. Photos are capped at 2200 px on the long edge, so the file stays emailable.

## The free tier

Up to 5 receipts per PDF. The paid unlock ($9 once) removes the limit and the footer mark. See
`PAYMENT.md` for what has to be connected before that button does anything — currently nothing is
for sale on the page, and the button says so.

## Run it locally

    py -3.10 -m http.server 8899
    # then open http://127.0.0.1:8899/

Open it over `http://`, not `file://` — the sample loader uses a canvas and a `file://` page taints it.

## Layout

    index.html                  the page and the tool UI
    combine-receipt-photos-into-one-pdf.html   the guide page that answers the search phrase
    how-to-organize-receipts-for-taxes.html    guide: organizing receipts for taxes
    reimbursement-claim-pdf.html               guide: a reimbursement claim PDF
    expense-report-with-receipts.html          guide: an expense report with receipts
    multiple-receipts-one-page-pdf.html        guide: multiple receipts in one PDF
    scan-receipts-to-pdf-on-a-phone.html       guide: doing it from a phone (no app, no upload)
    how-long-to-keep-receipts.html             guide: how long to keep receipts (CRA's six-year rule, quoted)
    how-long-to-keep-records-irs.html          guide: how long to keep records in the US (IRS's periods, quoted)
    robots.txt                  crawl rules + sitemap pointer
    sitemap.xml                 the twelve public URLs (landing page, eight guides, three downloads)
    assets/app.js               the whole tool, including the PDF builder
    assets/style.css            the theme
    assets/og-card.png          the social card (generated, see below)
    assets/vendor/pdf-lib.min.js  pdf-lib 1.17.1, vendored (MIT, see the LICENSE file beside it)
    downloads/receipts-sample.pdf       real output, unlocked build: 7 receipts, 8 pages, no footer mark
    downloads/receipts-sample-free.pdf  real output, free build: first 5 of the 7 receipts, 6 pages, the footer mark on every receipt page
    downloads/how-to-use.pdf            one-page instruction sheet
    samples/receipts/           7 sample receipts with made-up merchants, plus their manifest
    tools/                      scripts used to build the PDFs, check the output and archive the pages (see Checks below)
    discovery/wayback-references.json  one archive.org snapshot per public page (tools/archive-pages.py)
    recon/                      internal research, not published

`tools/check-pdf.py` opens a produced PDF and prints page count, page sizes and the text of every
page, and can render them to PNG. That is how the output was checked rather than eyeballed.

## Discovery

The site is a subpath of a shared host, so a crawler that reads no `robots.txt` at the host root has to
be told the URLs directly. Three things point at them, none of which needs an account:

- `sitemap.xml` lists the twelve public URLs (landing page, eight guides, three downloads).
- `tools/indexnow.py` reads that sitemap and POSTs the URL list to the IndexNow endpoints (Bing,
  Yandex and the engines that share the protocol). A build-time request, not an on-page one, so
  `connect-src 'none'` is untouched.
- `tools/archive-pages.py` gives every public page a permanent copy on the **Wayback Machine** — a
  reference that lives outside this project's own domain. It reads the URLs from `sitemap.xml`, asks
  archive.org to save each page, and confirms the capture against the CDX index (the
  `/wayback/available` API lags behind it, so it is reported but not trusted). The result is recorded
  in `discovery/wayback-references.json`; `--verify` re-checks it without saving anything new.

## Checks

    py -3.10 tools/verify_site.py            # check the working tree
    py -3.10 tools/verify_site.py --served   # also re-fetch the live site and compare

`verify_site.py` reads the receipt count, page count, KB figure, exact byte count and the footer-mark
claim straight out of `index.html` and compares each one to the PDF it names, byte for byte — so a page
edit that mis-states a file fails the check instead of a reader finding it. It also asserts `config.js`
keeps both constants empty (the paid door stays dormant until the rail exists) and that `assets/app.js`
still requires both halves before it renders a live buy link. Exit `0` = every check matched.

For the discovery surface it additionally asserts, per page: a title / description / self-canonical /
`og:image` / `twitter:card=summary_large_image`; that every indexable page is listed in `sitemap.xml`
and every `<loc>` names a file that exists; that no page loads a script, style, image or frame from
another origin (the machine check behind the `connect-src 'none'` promise — the GitHub `<a href>` is not
a subresource and is correctly not counted); and that `assets/og-card.png` is 1200×630. The phone guide
must be linked from the landing page and from a sibling guide. Every one of these was proven to go red
by mutating the real file (drop the sitemap entry, unlink the page, point `og:image` at a missing card,
widen the card, add an external script, drop the canonical) and green on the real tree.

It also asserts that every public page carries a Wayback snapshot: `discovery/wayback-references.json`
must cover every `<loc>` that is a page, and each entry must point at a real `web.archive.org` snapshot
whose 14-digit timestamp matches the recorded one and whose status is 200. Proven red by removing a
page's entry, by pointing an entry at a non-archive host, and by a non-200 status; green on the real
record. `tools/archive-pages.py --verify` re-checks the same snapshots against archive.org's CDX index.

The cited guides (`how-long-to-keep-receipts.html` for Canada, `how-long-to-keep-records-irs.html` for
the US) each get their own guard: the page must name its source URL(s), print a `Read YYYY-MM-DD` date
stamp, and carry the retention sentences **verbatim**, and its stated price and free cap must still
match `config.js` (`PRICE_USD`) and `assets/app.js` (`FREE_LIMIT`) — so a page cannot drift from the
product or quietly drop a quotation. Both pages are generated by `tools/make-keep-receipts-page.py`,
which fetches the government pages at build time, proves each sentence is on the page it is attributed
to, and **aborts without writing** if the source cannot be read — the quotes are never carried from
memory. Proven red by mutating all occurrences (alter a quote, remove the read date, drop a source URL,
change the free cap, tamper the rule sentence, unlink the page, drop its sitemap entry, add an external
script) and green on the real tree. With `--served`, `check_cited_sources_live()` additionally
re-fetches each named CRA/IRS page with the generator's own `fetch()` + `plain()` and re-asserts every
quoted sentence is still there, so the suite catches a government edit rather than only a re-run of the
generator — proven red when one sentence no longer matches the source and green on the real sources.

## Regenerating the artifacts

    py -3.10 samples/receipts/make_receipts.py     # the sample receipt images
    py -3.10 tools/shrink-samples.py               # PNG -> JPEG for the web
    py -3.10 tools/make-howto.py                   # downloads/how-to-use.pdf
    py -3.10 tools/make-og-card.py                 # assets/og-card.png (needs Pillow + pymupdf)
    py -3.10 tools/make-keep-receipts-page.py      # how-long-to-keep-receipts.html + how-long-to-keep-records-irs.html (fetches CRA + IRS; aborts if unreadable)
    py -3.10 tools/check-pdf.py downloads/receipts-sample.pdf --render out/

Both sample PDFs are regenerated by running the tool itself in a browser (the sample receipts are
made-up; no real receipt is in this repo). `receipts-sample.pdf` is the unlocked build — all 7 sample
receipts. `receipts-sample-free.pdf` is built through the free path with no unlock: load the 7 samples,
build, and the page's own 5-receipt cap and footer mark produce it.

## Not tax advice

It puts receipts in one file, in order, with a total. What you claim is your call.
