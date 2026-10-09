/* SPIKE — an expense-report cover sheet on the existing PDF engine.
   Dev artifact: not a product page, not linked from the site, not shipped code.

   The question this answers, from NEXT.md #8: can the engine that already lays
   out a covered, footed, multi-page document render a *second* first page — an
   expense report (period, total, per-category subtotals, signature line) — from
   a hand-made item list, without a new PDF engine?

   In order, this file:
     1. loads the seven sample receipt photos and normalises them with the
        tool's own exported normaliser (window.RS.normalizeImage);
     2. hands a hand-made item list (one category per row) to the tool's OWN
        buildPdf, unmodified — the exact code path that ships;
     3. takes that document and lays the expense-report cover sheet onto page 1
        with the same vendored pdf-lib, the same page geometry and the tool's
        own WinAnsi cleaner (window.RS.clean).
   It exposes the finished PDF as window.__spikeB64 for the caller to save, and
   records the CSP event log so the page can be measured, not assumed. */
(function () {
'use strict';

var PDFLib = window.PDFLib;

/* The whole point of the spike is that nothing here is a new engine: one page
   size, one margin, one palette, one type scale — the same numbers buildPdf
   uses for its own cover page. */
var PW = 612, PH = 792, M = 36, FOOT = 26;
var GREY = [0.42, 0.40, 0.35], INK = [0.10, 0.09, 0.08], RULE = [0.85, 0.82, 0.75];

function rgb(c) { return PDFLib.rgb(c[0], c[1], c[2]); }
function clean(s) { return window.RS.clean(s); }          // the tool's own cleaner, exported

/* buildPdf's money() is module-private; this is the same formatter, 9 lines. */
function money(n) {
  var neg = n < 0, v = Math.abs(n).toFixed(2).split('.');
  return (neg ? '-' : '') + '$' + v[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + v[1];
}
function amtOf(it) {
  var n = parseFloat(String(it.amount).replace(/[^0-9.\-]/g, ''));
  return isFinite(n) ? n : null;
}

/* The hand-made list. One category per row — that is the only field buildPdf
   does not already know about. */
var ITEMS = [
  { file: 'IMG_20260214_093012.jpg',     date: '2026-02-14', note: 'Northside Coffee Co. — client lunch',        amount: '18.75',  category: 'Meals' },
  { file: 'IMG_20260218_181244.jpg',     date: '2026-02-18', note: 'Harbour Hardware — fasteners and tape',      amount: '142.30', category: 'Materials' },
  { file: '2026-03-02_fuel.jpg',         date: '2026-03-02', note: 'Kingsway Fuel Stop — van, site run',         amount: '78.40',  category: 'Travel' },
  { file: 'Scan_20260305-1420.jpg',      date: '2026-03-05', note: 'Meridian Office Supply — paper, toner',      amount: '64.99',  category: 'Office' },
  { file: 'IMG_20260311_120501.jpg',     date: '2026-03-11', note: 'Blue Anchor Cafe — team meeting',            amount: '26.50',  category: 'Meals' },
  { file: 'receipt-novaprint-mar14.jpg', date: '2026-03-14', note: 'Novaprint Digital — banner print',           amount: '310.00', category: 'Print' },
  { file: 'IMG_20260320_081500.jpg',     date: '2026-03-20', note: 'Kingsway Fuel Stop — van, site run',         amount: '71.20',  category: 'Travel' }
];

var PREPARED_FOR = 'Acme Field Services Ltd.';
var TITLE = 'Expense Report';

/* ---------------------------------------------------------------- plumbing */

var logEl = null;
function log() {
  var parts = Array.prototype.slice.call(arguments).map(function (x) {
    return (x && typeof x === 'object') ? JSON.stringify(x) : String(x);
  });
  var line = parts.join(' ');
  if (logEl) { logEl.textContent += line + '\n'; }
}

function loadOne(src) {
  return new Promise(function (res, rej) {
    var img = new Image();
    img.onload = function () { res(img); };
    img.onerror = function () { rej(new Error('could not load ' + src)); };
    img.src = src;
  });
}

function b64(u8) {
  var s = '', CH = 0x8000, i;
  for (i = 0; i < u8.length; i += CH) {
    s += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
  }
  return btoa(s);
}

/* --------------------------------------------------- category subtotals */

function groupBy(items) {
  var order = [], map = {};
  items.forEach(function (it) {
    var c = it.category || 'Uncategorised';
    if (!map[c]) { map[c] = { cat: c, rows: [], sub: 0, entered: 0 }; order.push(c); }
    map[c].rows.push(it);
    var n = amtOf(it);
    if (n !== null) { map[c].sub += n; map[c].entered++; }
  });
  return order.map(function (c) { return map[c]; });
}

/* ------------------------------------------- the cover sheet (the new bits) */

function drawCoverSheet(doc, font, bold, meta) {
  var page = doc.insertPage(0, [PW, PH]);
  var top = PH - M, y = top;
  var cNo = M, cDate = M + 18, cCat = M + 86, cNote = M + 186, cAmt = PW - M;

  function line(yy, col, thick, x, width) {
    page.drawRectangle({
      x: (x === undefined ? M : x), y: yy,
      width: (width === undefined ? PW - 2 * M : width),
      height: thick || 0.7, color: rgb(col || RULE)
    });
  }
  function at(text, x, yy, f, size, col) {
    page.drawText(clean(text), { x: x, y: yy, size: size, font: f || font, color: rgb(col || INK) });
  }
  function atRight(text, xr, yy, f, size, col) {
    var t = clean(text);
    page.drawText(t, { x: xr - (f || font).widthOfTextAtSize(t, size), y: yy, size: size, font: f || font, color: rgb(col || INK) });
  }

  /* masthead — the same shape as buildPdf's own cover page */
  y = top - 8;
  at('ReceiptStack', M, y, bold, 9, GREY);
  atRight(meta.created, PW - M, y, font, 9, GREY);
  y -= 26;
  at(TITLE, M, y, bold, 24);
  y -= 20;
  at('Prepared for ' + meta.preparedFor + '  \u00b7  ' + meta.period + '  \u00b7  ' +
     meta.items.length + (meta.items.length === 1 ? ' expense' : ' expenses'), M, y, font, 10.5, GREY);
  y -= 22;
  line(y, INK, 1.2);
  y -= 22;

  /* the table: Date | Category | Note | Amount */
  at('Date', cDate, y, bold, 8, GREY);
  at('Category', cCat, y, bold, 8, GREY);
  at('Note', cNote, y, bold, 8, GREY);
  atRight('Amount', cAmt, y, bold, 8, GREY);
  line(y - 6, RULE, 0.7);
  y -= 24;

  var rowH = 16, groups = groupBy(meta.items);
  var floorY = M + 150;                       /* keep the signature block its own band */
  var spilled = 0;

  groups.forEach(function (g) {
    g.rows.forEach(function (it) {
      if (y < floorY) { spilled++; return; }
      at('', cNo, y, font, 10);
      at(it.date || '-', cDate, y, font, 10, it.date ? INK : GREY);
      at(g.cat, cCat, y, font, 10);
      at(fitOne(it.note || '', font, 10, cAmt - cNote - 8), cNote, y, font, 10);
      var n = amtOf(it);
      atRight(n === null ? '-' : money(n), cAmt, y, font, 10);
      y -= rowH;
    });
    if (spilled) return;
    y -= 2;
    at('Subtotal \u00b7 ' + g.cat, cCat, y, bold, 9, GREY);
    atRight(money(g.sub), cAmt, y, bold, 9);
    y -= 8;
    line(y, RULE, 0.5, cCat, cAmt - cCat);
    y -= 12;
  });

  if (spilled) {
    at(spilled + ' row' + (spilled === 1 ? '' : 's') + ' did not fit on this page', cCat, y, font, 9, GREY);
    y -= rowH;
  }

  y -= 2;
  line(y + 12, INK, 1);
  at('Total of ' + meta.entered + (meta.entered === 1 ? ' amount' : ' amounts'), cNote, y, bold, 10);
  atRight(money(meta.total), cAmt, y, bold, 11);

  /* the signature band */
  var sigY = M + 96, sigW = 210, gap = 26;
  var sigs = [
    { x: M,                       w: sigW,            label: 'Signature' },
    { x: M + sigW + gap,          w: 130,             label: 'Date' },
    { x: M + sigW + gap + 156,    w: PW - M - (M + sigW + gap + 156), label: 'Approved by (name)' }
  ];
  sigs.forEach(function (s) {
    line(sigY, RULE, 0.7, s.x, s.w);
    at(s.label, s.x, sigY - 12, font, 8.5, GREY);
  });

  at('Every receipt is on its own page after this one, in the order listed.', M, M + FOOT + 8, font, 8.5, GREY);
  return { spilled: spilled };
}

function fitOne(text, font, size, max) {
  var t = clean(text);
  if (font.widthOfTextAtSize(t, size) <= max) return t;
  while (t.length > 1 && font.widthOfTextAtSize(t + '...', size) > max) t = t.slice(0, -1);
  return t + '...';
}

/* ------------------------------------------------------------- the run */

function totals(items) {
  var total = 0, entered = 0;
  items.forEach(function (it) { var n = amtOf(it); if (n !== null) { total += n; entered++; } });
  var dated = items.filter(function (it) { return it.date; }).map(function (it) { return it.date; }).sort();
  return {
    total: total, entered: entered,
    period: dated.length ? (dated[0] + ' to ' + dated[dated.length - 1]) : 'dates not set'
  };
}

function runSpike() {
  var t0 = performance.now();
  logEl = document.getElementById('log');
  logEl.textContent = '';
  document.getElementById('status').textContent = 'Rendering\u2026';

  if (!PDFLib || !window.RS) {
    log('engine missing: PDFLib=' + !!PDFLib + ' window.RS=' + !!window.RS);
    document.getElementById('status').textContent = 'engine missing';
    return Promise.resolve(null);
  }

  var items = [];
  return ITEMS.reduce(function (chain, it, i) {
    return chain.then(function () {
      return loadOne('../samples/receipts/' + it.file);
    }).then(function (img) {
      return window.RS.normalizeImage(img, 0).then(function (n) {
        items.push({
          date: it.date, note: it.note, amount: it.amount, category: it.category,
          bytes: n.bytes, w: n.w, h: n.h
        });
        log('  loaded ' + it.file + ' \u2192 ' + n.w + 'x' + n.h + ' ' + n.bytes.length + ' B');
      });
    });
  }, Promise.resolve()).then(function () {
    log('hand-made list: ' + items.length + ' rows, ' + groupBy(items).length + ' categories');
    /* (1) THE EXISTING CODE PATH, unmodified */
    return window.RS.buildPdf(items, { title: TITLE, pageSize: 'letter', unlocked: false });
  }).then(function (out) {
    log('buildPdf \u2192 ' + out.pages + ' page(s), ' + out.bytes.length + ' B (untouched engine)');
    var t = totals(items);
    /* (2) THE COVER SHEET, same engine, inserted as page 1 */
    return PDFLib.PDFDocument.load(out.bytes).then(function (doc) {
      return Promise.all([
        doc.embedFont(PDFLib.StandardFonts.Helvetica),
        doc.embedFont(PDFLib.StandardFonts.HelveticaBold)
      ]).then(function (fonts) {
        var meta = {
          preparedFor: PREPARED_FOR,
          period: t.period, total: t.total, entered: t.entered,
          items: items, created: new Date().toISOString().slice(0, 10)
        };
        var r = drawCoverSheet(doc, fonts[0], fonts[1], meta);
        log('cover sheet: ' + groupBy(items).length + ' subtotals, signature band, spilled=' + r.spilled);
        return doc.save({ useObjectStreams: false }).then(function (bytes) {
          return { bytes: bytes, pages: doc.getPageCount(), basePages: out.pages, baseBytes: out.bytes.length };
        });
      });
    });
  }).then(function (res) {
    window.__spikeB64 = b64(res.bytes);
    window.__spike = {
      basePages: res.basePages, pages: res.pages,
      baseBytes: res.baseBytes, bytes: res.bytes.length,
      ms: Math.round(performance.now() - t0),
      csp: (window.__csp || []).slice(), errs: (window.__errs || []).slice()
    };
    var url = URL.createObjectURL(new Blob([res.bytes], { type: 'application/pdf' }));
    var a = document.createElement('a');
    a.href = url; a.download = 'expense-report-cover-sheet-spike.pdf';
    a.textContent = 'Download expense-report-cover-sheet-spike.pdf (' + res.bytes.length + ' B)';
    var out = document.getElementById('out');
    out.textContent = '';
    out.appendChild(a);
    document.getElementById('status').textContent =
      'done: ' + res.pages + ' pages, ' + res.bytes.length + ' B, ' +
      ((window.__csp || []).length) + ' CSP violations';
    log('spike PDF: ' + res.pages + ' pages (' + res.basePages + ' from buildPdf + 1 cover sheet), ' +
        res.bytes.length + ' B, ' + window.__spike.ms + ' ms');
    log('CSP violations: ' + JSON.stringify(window.__csp || []) + '  uncaught errors: ' + JSON.stringify(window.__errs || []));
    return window.__spike;
  }).catch(function (e) {
    document.getElementById('status').textContent = 'failed';
    log('FAILED: ' + (e && e.message ? e.message : e));
    window.__spikeError = String(e && e.stack ? e.stack : e);
    return null;
  });
}

window.spikeRun = runSpike;
window.spikeB64 = function () { return window.__spikeB64 || ''; };

function boot() {
  var btn = document.getElementById('runBtn');
  if (btn) btn.addEventListener('click', function () { runSpike(); });
  runSpike();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();

})();
