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
    robots.txt                  crawl rules + sitemap pointer
    sitemap.xml                 the ten public URLs (landing page, six guides, three downloads)
    assets/app.js               the whole tool, including the PDF builder
    assets/style.css            the theme
    assets/og-card.png          the social card (generated, see below)
    assets/vendor/pdf-lib.min.js  pdf-lib 1.17.1, vendored (MIT, see the LICENSE file beside it)
    downloads/receipts-sample.pdf       real output, unlocked build: 7 receipts, 8 pages, no footer mark
    downloads/receipts-sample-free.pdf  real output, free build: first 5 of the 7 receipts, 6 pages, the footer mark on every receipt page
    downloads/how-to-use.pdf            one-page instruction sheet
    samples/receipts/           7 sample receipts with made-up merchants, plus their manifest
    tools/                      scripts used to build the PDFs and check the output (see Checks below)
    recon/                      internal research, not published

`tools/check-pdf.py` opens a produced PDF and prints page count, page sizes and the text of every
page, and can render them to PNG. That is how the output was checked rather than eyeballed.

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

## Regenerating the artifacts

    py -3.10 samples/receipts/make_receipts.py     # the sample receipt images
    py -3.10 tools/shrink-samples.py               # PNG -> JPEG for the web
    py -3.10 tools/make-howto.py                   # downloads/how-to-use.pdf
    py -3.10 tools/make-og-card.py                 # assets/og-card.png (needs Pillow + pymupdf)
    py -3.10 tools/check-pdf.py downloads/receipts-sample.pdf --render out/

Both sample PDFs are regenerated by running the tool itself in a browser (the sample receipts are
made-up; no real receipt is in this repo). `receipts-sample.pdf` is the unlocked build — all 7 sample
receipts. `receipts-sample-free.pdf` is built through the free path with no unlock: load the 7 samples,
build, and the page's own 5-receipt cap and footer mark produce it.

## Not tax advice

It puts receipts in one file, in order, with a total. What you claim is your call.
