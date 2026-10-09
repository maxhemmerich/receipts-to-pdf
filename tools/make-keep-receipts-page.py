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
IRS_OUT = os.path.join(ROOT, "how-long-to-keep-records-irs.html")
HMRC_OUT = os.path.join(ROOT, "how-long-to-keep-records-hmrc.html")
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


# The one IRS page this track quotes, for the identical question in the United States. Same shape as
# the CRA block above: every sentence below is asserted present in the fetched page before it can be
# printed, so a quote is never carried from memory and a moved sentence stops the build.
IRS_SOURCES = {
    "irs": {
        "url": "https://www.irs.gov/businesses/small-businesses-self-employed/how-long-should-i-keep-records",
        "title": "How long should I keep records?",
        "sentences": [
            "Generally, you must keep your records that support an item of income, deduction or credit shown on your tax return until the period of limitations for that tax return runs out.",
            "The period of limitations is the period of time in which you can amend your tax return to claim a credit or refund, or the IRS can assess additional tax.",
            "Unless otherwise stated, the years refer to the period after the return was filed.",
            "Keep records for 3 years if situations (4), (5), and (6) below do not apply to you.",
            "Keep records for 6 years if you do not report income that you should report, and it is more than 25% of the gross income shown on your return.",
            "Keep records for 7 years if you file a claim for a loss from worthless securities or bad debt deduction.",
            "Keep records indefinitely if you do not file a return.",
            "Keep records indefinitely if you file a fraudulent return.",
            "Keep employment tax records for at least 4 years after the date that the tax becomes due or is paid, whichever is later.",
            "Keep copies of your filed tax returns.",
            "Generally, keep records relating to property until the period of limitations expires for the year in which you dispose of the property.",
            "When your records are no longer needed for tax purposes, do not discard them until you check to see if you have to keep them longer for other purposes.",
        ],
    },
}


# The third cited guide: the identical retention question for the United Kingdom, quoting HMRC's
# pages on gov.uk. Same shape as the CRA and IRS tracks -- every sentence below is asserted present
# in the fetched page before it can be printed, so a quote is never carried from memory and a moved
# sentence stops the build. Two gov.uk pages: the self-employed rule (5 years) and the limited
# company rule (6 years). A gov.uk sentence that wraps an inline <a> (e.g. the link around "HMRC")
# is deliberately not quoted: the fetched text normalises to "( HMRC )" with the link padding, which
# would print as a spacing defect, so only clean contiguous sentences are used.
HMRC_SOURCES = {
    "se": {
        "url": "https://www.gov.uk/self-employed-records/how-long-to-keep-your-records",
        "title": "Business records if you're self-employed: How long to keep your records",
        "sentences": [
            "You must keep your records for at least 5 years after the 31 January submission deadline of the relevant tax year.",
            "If you sent your 2022 to 2023 tax return online by 31 January 2024, you must keep your records until at least the end of January 2029.",
            "If you send your tax return more than 4 years after the deadline, you\u2019ll need to keep your records for 15 months after you send your tax return.",
            "If you cannot replace your records, you must do your best to provide figures.",
        ],
    },
    "ltd": {
        "url": "https://www.gov.uk/running-a-limited-company/company-and-accounting-records",
        "title": "Running a limited company: Company and accounting records",
        "sentences": [
            "You must keep records for 6 years from the end of the last company financial year they relate to, or longer if:",
            "all money spent by the company, for example receipts, petty cash books, orders and delivery notes",
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
  <a href="scan-receipts-to-pdf-on-a-phone.html">from a phone</a> &middot;
  <a href="how-long-to-keep-records-irs.html">how long to keep records in the US</a> &middot;
  <a href="how-long-to-keep-records-hmrc.html">how long to keep records in the UK</a></p>

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

  <section class="block" id="faq">
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

# The IRS page template, same shape as the CRA one: no quote text is written here, only [[TOKEN]]
# placeholders main() fills from the live irs.gov fetch.
IRS_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<title>How long should I keep records? &mdash; the IRS&rsquo;s periods of limitation, quoted | ReceiptStack</title>
<meta name="description" content="The IRS&rsquo;s own rule, quoted from irs.gov: generally, keep your records that support an item of income, deduction or credit until the period of limitations for that return runs out &mdash; 3 years in the ordinary case, longer in the situations the page lists. This page prints the source URL and the date it was read beside each quote.">
<link rel="canonical" href="https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-records-irs.html">
<meta name="theme-color" content="#f4f1e9">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ReceiptStack">
<meta property="og:title" content="How long should I keep records? &mdash; the IRS&rsquo;s periods of limitation">
<meta property="og:description" content="Quoted from irs.gov, with the source URL and the date it was read: keep your records until the period of limitations for that return runs out &mdash; 3 years in the ordinary case. No upload, no account.">
<meta property="og:url" content="https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-records-irs.html">
<meta property="og:image" content="https://maxhemmerich.github.io/receipts-to-pdf/assets/og-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The ReceiptStack index page: seven receipts listed with dates and amounts, total $712.14">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="How long should I keep records? &mdash; the IRS&rsquo;s periods of limitation">
<meta name="twitter:description" content="The IRS&rsquo;s own rule, quoted from irs.gov with the source URL and the date it was read.">
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
      "@id": "https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-records-irs.html#faq",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "How long should I keep records in the United States?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "The IRS's rule, quoted on this page from its own irs.gov page, is stated as a period rather than a number of years: generally, keep your records that support an item of income, deduction or credit until the period of limitations for that return runs out. Its page lists 3 years as the ordinary period, with longer periods in specific situations. The source URL and the date it was read are printed beside the quote."
          }
        },
        {
          "@type": "Question",
          "name": "Is that the same as the Canadian six-year rule?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "No. They are different jurisdictions with different rules. The Canada Revenue Agency's six-year rule is quoted on its own page; the Internal Revenue Service's periods are quoted on this one. Neither figure substitutes for the other."
          }
        },
        {
          "@type": "Question",
          "name": "What if I never filed a return?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Keep records indefinitely if you do not file a return."
          }
        },
        {
          "@type": "Question",
          "name": "Does ReceiptStack tell me what to keep or for how long?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "No. The retention rules are the IRS's and the CRA's, quoted from their pages. ReceiptStack only assembles the receipts you give it into one dated, indexed PDF, in your browser - nothing is uploaded, there is no account, and it makes no tax decisions."
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
  <h1>How long should I keep records?</h1>
  <p class="lede">In the United States this is not one number. The Internal Revenue Service states the
  rule as a period, not a fixed term: <b>keep your records until the period of limitations for that
  return runs out</b> &mdash; which its own page then spells out, 3 years in the ordinary case and
  longer in the situations it lists. This page quotes that from the IRS&rsquo;s own page, prints the
  source URL and the date it was read beside every quote, and is plain about the small part the rest of
  this site plays &mdash; turning a pile of receipt photos into one dated, indexed file, in your
  browser, with nothing uploaded.</p>
  <p><a href="./#tool">Open the tool</a> &middot; <a href="downloads/receipts-sample.pdf">see a real
  output first</a> &middot; <a href="how-long-to-keep-receipts.html">how long to keep receipts in
  Canada</a> &middot; <a href="how-to-organize-receipts-for-taxes.html">how to organize receipts for
  taxes</a> &middot; <a href="combine-receipt-photos-into-one-pdf.html">combine receipt photos into one
  PDF</a> &middot; <a href="reimbursement-claim-pdf.html">for a reimbursement claim</a> &middot;
  <a href="expense-report-with-receipts.html">for an expense report</a> &middot;
  <a href="multiple-receipts-one-page-pdf.html">multiple receipts in one PDF</a> &middot;
  <a href="scan-receipts-to-pdf-on-a-phone.html">from a phone</a> &middot;
  <a href="how-long-to-keep-records-hmrc.html">how long to keep records in the UK</a></p>

  <section class="block">
    <h2>The rule: until the period of limitations runs out</h2>
    <p>The IRS answers this question with a period rather than a flat number of years. Its rule is one
    sentence:</p>
    <blockquote cite="[[IRS_URL]]">[[IRS_RULE]]</blockquote>
    [[CITE_IRS]]
    <p>That phrase &mdash; <i>the period of limitations</i> &mdash; is the whole answer, so here is the
    IRS defining it in the next paragraph of the same page:</p>
    <blockquote cite="[[IRS_URL]]">[[IRS_DEF]]</blockquote>
    <p class="dim">From the same page: [[IRS_AFTER_FILED]]</p>
  </section>

  <section class="block">
    <h2>How long that period is, in the IRS&rsquo;s own numbers</h2>
    <p>For an income tax return the IRS lists the periods below on the same page. Each line is its own
    wording, quoted, not a summary. The first line cites the IRS&rsquo;s own numbering; those are the
    exceptions further down its page.</p>
    <dl class="facts">
      <dt>The ordinary case</dt>
      <dd>[[IRS_3YR]] <span class="dim">&mdash; IRS, <i>How long should I keep records?</i></span></dd>
      <dt>A loss from worthless securities or a bad debt</dt>
      <dd>[[IRS_7YR]] <span class="dim">&mdash; same IRS page.</span></dd>
      <dt>Under-reporting income by more than 25%</dt>
      <dd>[[IRS_6YR]] <span class="dim">&mdash; same IRS page.</span></dd>
      <dt>No return filed, or a fraudulent one</dt>
      <dd>[[IRS_INDEF_NF]] [[IRS_INDEF_FRAUD]] <span class="dim">&mdash; same IRS page.</span></dd>
      <dt>Employment tax records</dt>
      <dd>[[IRS_EMPLOY]] <span class="dim">&mdash; same IRS page.</span></dd>
    </dl>
    <p>Two more sentences from that page matter when the record is not a receipt. On the return itself:
    [[IRS_FILED_COPY]] For anything you own, the same page says: [[IRS_PROPERTY]]</p>
    <p class="dim">Read the wording closely: [[IRS_NONTAX]] &mdash; the tax periods above are not the
    only reason you might have to keep a document.</p>
  </section>

  <section class="block">
    <h2>What this page is not</h2>
    <p>This is a quotation of a published rule, not tax advice. It does not know your situation &mdash;
    whether you filed on time, whether a claim for refund or a bad debt is involved, or whether some
    other rule already requires you to keep a document longer. Where the periods above are not the whole
    answer for you, the page linked here is the source, and your accountant is the person to ask.</p>
    <p>The tool on the rest of this site makes no tax claim at all. It does not decide what you can
    claim, does not compute a deduction, and does not track any retention period for you. It builds a
    PDF.</p>
  </section>

  <section class="block">
    <h2>Making receipts you can keep</h2>
    <p>Whichever period applies to you, the record has to survive it. Paper makes that hard: a thermal
    till receipt left in a drawer or a car can fade to unreadable inside a year, well before the period
    is up. A photograph taken the day you get the receipt is the copy that survives the wait &mdash; and
    a dated, indexed file of those photographs is the copy you can actually lay hands on when you need
    it.</p>
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

  <section class="block" id="faq">
    <h2>Questions</h2>
    <dl class="facts">
      <dt>How long should I keep records in the United States?</dt>
      <dd>The IRS&rsquo;s own page states it as a period, not a number of years. Its rule, quoted above
      from irs.gov, is: <i>&ldquo;[[IRS_RULE_LEDE]]&rdquo;</i> Its page then lists 3 years as the
      ordinary period, longer in the cases quoted above.</dd>
      <dt>Is that the same as the Canadian six-year rule?</dt>
      <dd>No &mdash; they are different jurisdictions with different rules. The CRA&rsquo;s six-year
      rule is quoted on <a href="how-long-to-keep-receipts.html">its own page</a>; the US periods are
      the IRS&rsquo;s, quoted here. Neither figure is a substitute for the other.</dd>
      <dt>What if I never filed a return?</dt>
      <dd>[[IRS_INDEF_NF]] &mdash; quoted from the IRS&rsquo;s page, linked below.</dd>
      <dt>Does ReceiptStack tell me what to keep or for how long?</dt>
      <dd>No. The retention rules are the IRS&rsquo;s and the CRA&rsquo;s, and are quoted from their
      pages. ReceiptStack only assembles the receipts you give it into one dated, indexed PDF, in your
      browser &mdash; nothing is uploaded, there is no account, and it makes no tax decisions.</dd>
      <dt>How many receipts can I put in one PDF?</dt>
      <dd>Free for a PDF of up to 5 receipts, index and totals included, with no account and no email.
      Above that, a one-time $9 unlock removes the limit and the small footer mark.</dd>
    </dl>
  </section>

  <section class="block">
    <h2>Sources</h2>
    <p class="dim">Every quotation on this page was read from this Internal Revenue Service page on
    [[DATE_READ]] ([[DATE_READ_LONG]]), and the sentence was matched against the page at build time.
    IRS material is a U.S. Government work and is in the public domain.</p>
    <ul class="dim">
      <li>Internal Revenue Service &mdash; <i>How long should I keep records?</i><br>
      <a href="[[IRS_URL]]">[[IRS_URL]]</a><br>
      Page last reviewed or updated [[IRS_MOD]].</li>
    </ul>
  </section>

  <footer class="foot">
    <p><a href="./">ReceiptStack</a> &mdash; one page, no backend. <a href="https://github.com/maxhemmerich/receipts-to-pdf">Source</a>.</p>
    <p class="dim">Not tax advice. The retention periods above are the IRS&rsquo;s, quoted with their source; this tool puts your receipts in one file and nothing more.</p>
  </footer>

</main>

</body>
</html>
'''


# The UK page template, same shape as the CRA and IRS ones: no quote text is written here, only
# [[TOKEN]] placeholders main() fills from the live gov.uk fetch.
HMRC_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<title>How long do I have to keep receipts in the UK? &mdash; HMRC&rsquo;s rule, quoted | ReceiptStack</title>
<meta name="description" content="HMRC&rsquo;s own rule, quoted from gov.uk: if you&rsquo;re self-employed you must keep your records for at least 5 years after the 31 January submission deadline of the relevant tax year, and a limited company must keep records for 6 years from the end of the last company financial year they relate to. This page prints the source URL and the date it was read beside every quote.">
<link rel="canonical" href="https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-records-hmrc.html">
<meta name="theme-color" content="#f4f1e9">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ReceiptStack">
<meta property="og:title" content="How long do I have to keep receipts in the UK? &mdash; HMRC&rsquo;s rule">
<meta property="og:description" content="Quoted from gov.uk, with the source URL and the date it was read: at least 5 years for a sole trader, 6 years for a limited company. No upload, no account.">
<meta property="og:url" content="https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-records-hmrc.html">
<meta property="og:image" content="https://maxhemmerich.github.io/receipts-to-pdf/assets/og-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The ReceiptStack index page: seven receipts listed with dates and amounts, total $712.14">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="How long do I have to keep receipts in the UK? &mdash; HMRC&rsquo;s rule">
<meta name="twitter:description" content="HMRC&rsquo;s own rule, quoted from gov.uk with the source URL and the date it was read.">
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
      "@id": "https://maxhemmerich.github.io/receipts-to-pdf/how-long-to-keep-records-hmrc.html#faq",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "How long do I have to keep receipts in the UK?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "If you are self-employed, HMRC's own rule, quoted on this page from gov.uk, is at least 5 years after the 31 January submission deadline of the relevant tax year. If you run a limited company it is 6 years from the end of the last company financial year the records relate to. The source URL and the date it was read are printed beside each quote."
          }
        },
        {
          "@type": "Question",
          "name": "Does the same period apply to a limited company?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "No. A sole trader keeps records for at least 5 years; a limited company must keep records for 6 years from the end of the last company financial year they relate to. HMRC's 6-year sentence is quoted on this page, on its own gov.uk page."
          }
        },
        {
          "@type": "Question",
          "name": "What if I file my tax return late?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "HMRC's own page says if you send your tax return more than 4 years after the deadline, you'll need to keep your records for 15 months after you send your tax return. That sentence is quoted, with its source, further down this page."
          }
        },
        {
          "@type": "Question",
          "name": "Does ReceiptStack tell me what to keep or for how long?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "No. The retention rules are HMRC's and are quoted from its pages. ReceiptStack only assembles the receipts you give it into one dated, indexed PDF, in your browser - nothing is uploaded, there is no account, and it makes no tax decisions."
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
  <h1>How long do I have to keep receipts in the UK?</h1>
  <p class="lede">HMRC answers this with different numbers depending on who you are: at least
  <b>5 years</b> for a sole trader, and <b>6 years</b> for a limited company. This page quotes the rule
  from HMRC&rsquo;s own gov.uk pages, prints the source URL and the date it was read beside every quote,
  and is plain about the small part the rest of this site plays &mdash; turning a pile of receipt photos
  into one dated, indexed file, in your browser, with nothing uploaded.</p>
  <p><a href="./#tool">Open the tool</a> &middot; <a href="downloads/receipts-sample.pdf">see a real
  output first</a> &middot; <a href="how-long-to-keep-receipts.html">how long to keep receipts in
  Canada</a> &middot; <a href="how-long-to-keep-records-irs.html">how long to keep records in the
  US</a> &middot; <a href="how-to-organize-receipts-for-taxes.html">how to organize receipts for
  taxes</a> &middot; <a href="combine-receipt-photos-into-one-pdf.html">combine receipt photos into one
  PDF</a> &middot; <a href="reimbursement-claim-pdf.html">for a reimbursement claim</a> &middot;
  <a href="expense-report-with-receipts.html">for an expense report</a> &middot;
  <a href="multiple-receipts-one-page-pdf.html">multiple receipts in one PDF</a> &middot;
  <a href="scan-receipts-to-pdf-on-a-phone.html">from a phone</a></p>

  <section class="block">
    <h2>The short answer: 5 years if you are self-employed</h2>
    <p>For a sole trader or anyone filing a Self Assessment return, HMRC&rsquo;s rule is one sentence:</p>
    <blockquote cite="[[HMRC_SE_URL]]">[[HMRC_SE5]]</blockquote>
    [[CITE_SE]]
    <p>Read that closely, because the clock does not start on the day you get the receipt. It runs from
    the 31 January submission deadline of the <i>relevant tax year</i>, so a return for one year sets the
    date five years later. HMRC gives its own worked example:</p>
    <blockquote cite="[[HMRC_SE_URL]]">[[HMRC_SE_EXAMPLE]]</blockquote>
    <p class="dim">Same gov.uk page. A receipt from a later purchase in the same tax year is kept for the
    same period, not for five years from its own date.</p>
  </section>

  <section class="block">
    <h2>The 6-year rule for a limited company</h2>
    <p>A limited company keeps its records for longer, and HMRC&rsquo;s page says so in the same shape:</p>
    <blockquote cite="[[HMRC_LTD_URL]]">[[HMRC_LTD6]]</blockquote>
    [[CITE_LTD]]
    <p>The list that colon introduces names the cases that carry the period further &mdash; a transaction
    that spans more than one accounting period, an asset bought to last more than six years, a late
    Company Tax Return, or an open compliance check. And a receipt is on HMRC&rsquo;s own list of what
    those records are meant to include; its page says the accounting records must include
    [[HMRC_LTD_RECEIPTS]].</p>
  </section>

  <section class="block">
    <h2>The details the same gov.uk page gives</h2>
    <p>Two more sentences from HMRC answer the questions people ask next. Each is quoted, with its
    page.</p>
    <dl class="facts">
      <dt>Filed very late?</dt>
      <dd>[[HMRC_SE_LATE]] <span class="dim">&mdash; HMRC, <i>How long to keep your records</i>.</span></dd>
      <dt>If the records are lost or destroyed?</dt>
      <dd>[[HMRC_SE_LOST]] <span class="dim">&mdash; same HMRC page.</span></dd>
    </dl>
  </section>

  <section class="block">
    <h2>What this page is not</h2>
    <p>This is a quotation of a published rule, not tax advice or professional advice. It does not know
    your situation &mdash; whether you trade alone or through a company, whether VAT or PAYE records are
    involved, or whether HMRC has told you to keep something longer. Where the rule above is not the
    whole answer for you, the gov.uk pages linked here are the source, and your accountant is the person
    to ask.</p>
    <p>The tool on the rest of this site makes no tax claim at all. It does not decide what you can
    claim, does not compute a deduction, and does not track any retention period for you. It builds a
    PDF.</p>
  </section>

  <section class="block">
    <h2>Making receipts you can keep</h2>
    <p>Whichever period applies to you, the record has to survive it. Paper makes that hard: a thermal
    till receipt left in a drawer or a car can fade to unreadable inside a year, well before the period
    is up. A photograph taken the day you get the receipt is the copy that survives the wait &mdash; and
    a dated, indexed file of those photographs is the copy you can actually lay hands on when you need
    it.</p>
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

  <section class="block" id="faq">
    <h2>Questions</h2>
    <dl class="facts">
      <dt>How long do I have to keep receipts in the UK?</dt>
      <dd>If you are self-employed, HMRC&rsquo;s rule is at least 5 years after the 31 January submission
      deadline of the relevant tax year. If you run a limited company it is 6 years from the end of the
      last company financial year the records relate to. Both sentences are quoted above from HMRC&rsquo;s
      own gov.uk pages, with the source and the date they were read.</dd>
      <dt>Does the same period apply to a limited company?</dt>
      <dd>No. A sole trader keeps records for at least 5 years; a limited company must keep records for
      6 years from the end of the last company financial year they relate to &mdash; HMRC&rsquo;s 6-year
      sentence is quoted above, on its own gov.uk page.</dd>
      <dt>What if I file my tax return late?</dt>
      <dd>[[HMRC_SE_LATE]] &mdash; quoted from HMRC&rsquo;s gov.uk page, linked above.</dd>
      <dt>Does ReceiptStack tell me what to keep or for how long?</dt>
      <dd>No. The retention rules are HMRC&rsquo;s and are quoted from its pages. ReceiptStack only
      assembles the receipts you give it into one dated, indexed PDF, in your browser &mdash; nothing is
      uploaded, there is no account, and it makes no tax decisions.</dd>
      <dt>How many receipts can I put in one PDF?</dt>
      <dd>Free for a PDF of up to 5 receipts, index and totals included, with no account and no email.
      Above that, a one-time $9 unlock removes the limit and the small footer mark.</dd>
    </dl>
  </section>

  <section class="block">
    <h2>Sources</h2>
    <p class="dim">Every quotation on this page was read from the HM Revenue &amp; Customs pages on
    gov.uk on [[DATE_READ]] ([[DATE_READ_LONG]]), and the sentence was matched against the page at build
    time. Contains public sector information licensed under the Open Government Licence v3.0.</p>
    <ul class="dim">
      <li>HM Revenue &amp; Customs &mdash; <i>Business records if you&rsquo;re self-employed: How long to keep your records</i><br>
      <a href="[[HMRC_SE_URL]]">[[HMRC_SE_URL]]</a><br>
      gov.uk page last modified [[HMRC_SE_MOD]].</li>
      <li>HM Revenue &amp; Customs &mdash; <i>Running a limited company: Company and accounting records</i><br>
      <a href="[[HMRC_LTD_URL]]">[[HMRC_LTD_URL]]</a><br>
      gov.uk page last modified [[HMRC_LTD_MOD]].</li>
    </ul>
  </section>

  <footer class="foot">
    <p><a href="./">ReceiptStack</a> &mdash; one page, no backend. <a href="https://github.com/maxhemmerich/receipts-to-pdf">Source</a>.</p>
    <p class="dim">Not tax advice. The retention rules above are HMRC&rsquo;s, quoted with their source; this tool puts your receipts in one file and nothing more.</p>
  </footer>

</main>

</body>
</html>
'''


def render_hmrc(quotes, meta, read):
    """The UK page. Every [[HMRC_*]] token is filled from the verbatim gov.uk quotes, never typed here."""
    se = HMRC_SOURCES["se"]
    ltd = HMRC_SOURCES["ltd"]
    q = quotes["se"]
    ql = quotes["ltd"]

    def g(d, sentence):
        return html.escape(d[sentence])

    def cite(key, src):
        return ('<p class="cite">Source: HM Revenue &amp; Customs &mdash; <i>%s</i>. '
                '<a href="%s">%s</a><br>Read %s &middot; gov.uk page last modified %s. '
                'Contains public sector information licensed under the Open Government Licence v3.0.</p>'
                % (html.escape(src["title"]), src["url"], src["url"],
                   read.isoformat(), meta[key] or "unknown"))

    read_long = "%d %s %d" % (read.day, read.strftime("%B"), read.year)

    page = (HMRC_TEMPLATE
            .replace("[[DATE_READ]]", read.isoformat())
            .replace("[[DATE_READ_LONG]]", read_long)
            .replace("[[HMRC_SE_URL]]", se["url"])
            .replace("[[HMRC_LTD_URL]]", ltd["url"])
            .replace("[[HMRC_SE_MOD]]", html.escape(meta["se"] or "unknown"))
            .replace("[[HMRC_LTD_MOD]]", html.escape(meta["ltd"] or "unknown"))
            .replace("[[CITE_SE]]", cite("se", se))
            .replace("[[CITE_LTD]]", cite("ltd", ltd))
            .replace("[[HMRC_SE5]]", g(q, "You must keep your records for at least 5 years after the 31 January submission deadline of the relevant tax year."))
            .replace("[[HMRC_SE_EXAMPLE]]", g(q, "If you sent your 2022 to 2023 tax return online by 31 January 2024, you must keep your records until at least the end of January 2029."))
            .replace("[[HMRC_SE_LATE]]", g(q, "If you send your tax return more than 4 years after the deadline, you\u2019ll need to keep your records for 15 months after you send your tax return."))
            .replace("[[HMRC_SE_LOST]]", g(q, "If you cannot replace your records, you must do your best to provide figures."))
            .replace("[[HMRC_LTD6]]", g(ql, "You must keep records for 6 years from the end of the last company financial year they relate to, or longer if:"))
            .replace("[[HMRC_LTD_RECEIPTS]]", g(ql, "all money spent by the company, for example receipts, petty cash books, orders and delivery notes")))

    assert "[[" not in page, "make-keep-receipts-page: an unsubstituted placeholder remains (HMRC page)"
    return page


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
    if m:
        return m.group(1)
    # the gov.uk pages declare their content date in a meta tag (mirrored in their dateModified JSON-LD).
    m = re.search(r'name="govuk:public-updated-at"[^>]*content="([^"]+)"', raw)
    if m:
        return m.group(1)[:10]
    # the IRS page carries no dcterms meta; it prints the date as visible text.
    m = re.search(r"Page Last Reviewed or Updated:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", raw)
    return m.group(1) if m else None


def fetch_and_verify(sources, label):
    """Fetch each source page and prove every allowed sentence is present verbatim.

    Returns (quotes, meta). Aborts -- and writes nothing -- if a page cannot be read or a sentence is
    not found where it is claimed to be, so a quote is never carried from memory.
    """
    quotes = {}
    meta = {}
    for key, src in sources.items():
        code, raw = fetch(src["url"])
        print("fetch %-4s %-6s -> HTTP %s" % (label, key, code))
        if code != 200 or not raw:
            sys.exit("ABORT: could not read %s (HTTP %s). No page written; a quote is never "
                     "carried from memory." % (src["url"], code))
        text = plain(raw)
        for s in src["sentences"]:
            if plain(s) not in text:
                sys.exit("ABORT: the sentence %r was not found verbatim on %s. The source may have "
                         "changed the page -- refusing to publish a quote it can no longer stand "
                         "behind." % (s[:60], src["url"]))
        quotes[key] = {s: plain(s) for s in src["sentences"]}
        meta[key] = date_modified(raw)
        print("  ok  %d/%d sentences verified verbatim; page last modified %s"
              % (len(src["sentences"]), len(src["sentences"]), meta[key]))
    return quotes, meta


def render_cra(quotes, meta, read):
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

    assert "[[" not in page, "make-keep-receipts-page: an unsubstituted placeholder remains (CRA page)"
    return page


def render_irs(quotes, meta, read):
    """The IRS page. Every [[IRS_*]] token is filled from the verbatim quotes, never typed here."""
    src = IRS_SOURCES["irs"]
    q = quotes["irs"]

    def g(sentence):
        return html.escape(q[sentence])

    def cite():
        return ('<p class="cite">Source: Internal Revenue Service &mdash; <i>%s</i>. '
                '<a href="%s">%s</a><br>Read %s &middot; irs.gov page last reviewed or updated %s. '
                'U.S. Government work, public domain.</p>'
                % (html.escape(src["title"]), src["url"], src["url"],
                   read.isoformat(), meta["irs"] or "unknown"))

    read_long = "%d %s %d" % (read.day, read.strftime("%B"), read.year)

    page = (IRS_TEMPLATE
            .replace("[[DATE_READ]]", read.isoformat())
            .replace("[[DATE_READ_LONG]]", read_long)
            .replace("[[IRS_URL]]", src["url"])
            .replace("[[IRS_MOD]]", html.escape(meta["irs"] or "unknown"))
            .replace("[[CITE_IRS]]", cite())
            .replace("[[IRS_RULE_LEDE]]", g("Generally, you must keep your records that support an item of income, deduction or credit shown on your tax return until the period of limitations for that tax return runs out."))
            .replace("[[IRS_RULE]]", g("Generally, you must keep your records that support an item of income, deduction or credit shown on your tax return until the period of limitations for that tax return runs out."))
            .replace("[[IRS_DEF]]", g("The period of limitations is the period of time in which you can amend your tax return to claim a credit or refund, or the IRS can assess additional tax."))
            .replace("[[IRS_AFTER_FILED]]", g("Unless otherwise stated, the years refer to the period after the return was filed."))
            .replace("[[IRS_3YR]]", g("Keep records for 3 years if situations (4), (5), and (6) below do not apply to you."))
            .replace("[[IRS_7YR]]", g("Keep records for 7 years if you file a claim for a loss from worthless securities or bad debt deduction."))
            .replace("[[IRS_6YR]]", g("Keep records for 6 years if you do not report income that you should report, and it is more than 25% of the gross income shown on your return."))
            .replace("[[IRS_INDEF_NF]]", g("Keep records indefinitely if you do not file a return."))
            .replace("[[IRS_INDEF_FRAUD]]", g("Keep records indefinitely if you file a fraudulent return."))
            .replace("[[IRS_EMPLOY]]", g("Keep employment tax records for at least 4 years after the date that the tax becomes due or is paid, whichever is later."))
            .replace("[[IRS_FILED_COPY]]", g("Keep copies of your filed tax returns."))
            .replace("[[IRS_PROPERTY]]", g("Generally, keep records relating to property until the period of limitations expires for the year in which you dispose of the property."))
            .replace("[[IRS_NONTAX]]", g("When your records are no longer needed for tax purposes, do not discard them until you check to see if you have to keep them longer for other purposes.")))

    assert "[[" not in page, "make-keep-receipts-page: an unsubstituted placeholder remains (IRS page)"
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify the quotes, write nothing")
    ap.add_argument("--page", choices=["cra", "irs", "hmrc", "both"], default="both",
                    help="which cited page to build (default: both)")
    a = ap.parse_args()

    read = date.today()
    builds = []
    if a.page in ("cra", "both"):
        builds.append(("CRA", SOURCES, OUT, render_cra))
    if a.page in ("irs", "both"):
        builds.append(("IRS", IRS_SOURCES, IRS_OUT, render_irs))
    if a.page in ("hmrc", "both"):
        builds.append(("HMRC", HMRC_SOURCES, HMRC_OUT, render_hmrc))

    for label, sources, out, render in builds:
        quotes, meta = fetch_and_verify(sources, label)
        if a.check:
            print("check only: %s NOT written." % os.path.basename(out))
            continue
        page = render(quotes, meta, read)
        open(out, "w", newline="\n", encoding="utf-8").write(page)
        print("wrote %s (%d bytes), quotes read %s"
              % (os.path.relpath(out, ROOT), len(page.encode("utf-8")), read.isoformat()))


if __name__ == "__main__":
    main()
