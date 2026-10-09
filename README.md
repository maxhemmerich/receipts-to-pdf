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
    downloads/receipts-sample-free.pdf  real output, free build: first 5 of the 7 receipts, 6 pages, the footer mark on every receipt page — and that mark carries the tool's own address (maxhemmerich.github.io/receipts-to-pdf)
    downloads/how-to-use.pdf            one-page instruction sheet (carries the tool's address and the $9 price)
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
  in `discovery/wayback-references.json`; `--verify` re-checks it without saving anything new, and
  `--refresh` re-saves every URL — the captures are taken at a point in time, so a page whose content
  changed after its capture is re-archived instead of the record silently keeping the older revision.

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

It also asserts, per page, that every `FAQPage` in the page's JSON-LD describes content a reader can
actually see: the `@id` fragment must resolve to an element id on the page, and every marked-up
`Question` name must appear in the page's visible text. The landing page carried a six-question
`FAQPage` that was nowhere on the page and no `#faq` anchor, so its structured data described invisible
content and the fragment 404'd; the landing now shows a **Questions** section mirroring that JSON-LD
word for word, every page carries the `#faq` anchor its schema names, and the IRS page's one drifted
question name is aligned to the question the reader sees. Proven red by renaming a marked-up question,
deleting the visible section, dropping an anchor, and renaming the IRS question; green on the real
tree. The guard compares question names, not answers: the cited pages print their answers as prose that
quotes a sentence fetched at build time, so an answer is not a fixed string there.

It also asserts that the free build's footer mark carries the tool's own address: every receipt
page of `downloads/receipts-sample-free.pdf` must print both the product line and
`maxhemmerich.github.io/receipts-to-pdf`, the address must not appear on the free sample's index
page, and the paid sample must carry neither. The one PDF a free user emails to an accountant is
a free build, so the mark on it is the only thing in it that can lead a reader back to the tool.
Proven red by swapping in a free sample whose mark carries no address and by putting the paid
sample in the free slot (no mark at all); green on the real tree.

It also asserts that every public page carries a Wayback snapshot: `discovery/wayback-references.json`
must cover every `<loc>` that is a page, and each entry must point at a real `web.archive.org` snapshot
whose 14-digit timestamp matches the recorded one and whose status is 200. Proven red by removing a
page's entry, by pointing an entry at a non-archive host, and by a non-200 status; green on the real
record. `tools/archive-pages.py --verify` re-checks the same snapshots against archive.org's CDX index.

It also asserts that the one-page sheet leads back to the tool: `downloads/how-to-use.pdf` is itself a
public URL (it is in `sitemap.xml`, POSTed to IndexNow and archived on Wayback), so a reader can reach it
directly, and it is the sheet a reader keeps, prints and forwards. It must therefore carry the tool's
address, state the price **as `config.js` has it**, and carry a link to the site; it must also stay one
page, the count the landing page prints beside it. The sheet's generator reads `PRICE_USD` out of
`config.js` and the landing URL out of `sitemap.xml`, so neither can drift — and the check reads the same
two sources. Proven red by a sheet with no address, one with the wrong price, one with no link, and one
that spilled to two pages; green on the real file.

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

## The unlock, proven end to end — 2026-10-09

The paid door had only ever been checked as a *door*: it renders correctly in every state, but with
`config.js` carrying both constants empty no code had ever been typed in and accepted, so the two
things the $9 buys — the 5-receipt cap lifting and the footer mark coming off — were asserted, not
seen. They have now been driven through the shipped files in a real browser.

The harness is a **scratch copy of this site outside the repository** (never committed, the live
`config.js` untouched): the same `index.html`, `assets/app.js` and sample receipts, served over
`http://127.0.0.1` with `CHECKOUT_URL` set to a placeholder link and `UNLOCK_CODE` set to the digest
of a freshly minted test code. Mint it with the tool that ships here:

    py -3.10 tools/mint-unlock-code.py     # prints the CODE (to the buyer) and its DIGEST (config.js)

The page derives `PBKDF2-HMAC-SHA256(normalise(code), "receiptstack.unlock.v1", 210000, 32 bytes)` in
WebCrypto and compares the hex with `UNLOCK_CODE`; nothing leaves the tab, which is why the check runs
under `connect-src 'none'` unchanged. Observed in the harness:

- a **wrong** code → *"That code was not recognised."*, and the cap stays at 5;
- the **right** code → *"Unlocked. Add as many receipts as you like."*, the cap note and the limit line
  disappear, `receiptstack.unlocked` is stored, and the button becomes *"Unlocked on this browser"*;
- the unlocked build of all 7 sample receipts is **8 pages, 648 KB, no footer mark**, footers
  `Receipt n of 7`, index in date order with the total — structurally identical to
  `downloads/receipts-sample.pdf` (page text equal on every page; the only differing object is the
  cover's build-date stamp), while the same page still locked builds the 5-receipt, marked file that
  matches `downloads/receipts-sample-free.pdf`;
- the whole thing with **zero CSP violations, zero JS errors, and no `fetch` / XHR / `sendBeacon` /
  WebSocket call ever made** — the unlock is a local computation.

**The harness was proven able to fail before it was trusted:** flipping one hex character of the digest
in the served `config.js` makes the *correct* code come back *"That code was not recognised."*; restoring
the digest and retyping the same code unlocks. RED then GREEN, so the acceptance above is a real
comparison and not an unconditional unlock. Re-run it before the rail goes live, and again with the real
code the day Max's store mints one — the procedure is the same, only the digest is.

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
