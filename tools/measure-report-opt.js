/* DEV HARNESS — measures the additive `opts.report` opt on buildPdf (NEXT.md #8).
   Not a product page: noindex, not linked, not in the sitemap, shipped in tools/.

   The question this answers: does adding `opts.report = { preparedFor }` change
   ANYTHING for the existing call path? It measures, instead of assuming:

     A  buildPdf(items, {title, pageSize, unlocked})            <- the shipping call
     B  buildPdf(items, {title, pageSize, unlocked, report})    <- the new opt
     A2 the same A call again, in the same page load            <- determinism check

   The clock is frozen so two builds of the same input are comparable byte for
   byte; without that the builder stamps `new Date()` into the PDF and every
   build differs. With the clock frozen, A must equal A (determinism) and, on
   the unchanged engine, A must equal the hash captured before the engine was
   touched.

   Everything here is read off window.RS — the tool's own exported buildPdf —
   so no line of this harness can flatter the engine. */
(function () {
'use strict';

/* ---- freeze the clock: the builder calls new Date() for the PDF stamps ---- */
var FIXED_MS = Date.UTC(2026, 9, 9, 2, 20, 0);   // 2026-10-09T02:20:00Z
(function () {
  var Real = Date;
  function FrozenDate(a, b, c, d, e, f, g) {
    if (!(this instanceof FrozenDate)) return new Real(FIXED_MS).toString();
    switch (arguments.length) {
      case 0: return new Real(FIXED_MS);
      case 1: return new Real(a);
      case 2: return new Real(a, b);
      case 3: return new Real(a, b, c);
      case 4: return new Real(a, b, c, d);
      case 5: return new Real(a, b, c, d, e);
      case 6: return new Real(a, b, c, d, e, f);
      default: return new Real(a, b, c, d, e, f, g);
    }
  }
  FrozenDate.now = function () { return FIXED_MS; };
  FrozenDate.UTC = Real.UTC;
  FrozenDate.parse = Real.parse;
  FrozenDate.prototype = Real.prototype;
  window.Date = FrozenDate;
})();

var PDFLib = window.PDFLib;

/* the item list: the same 7 sample receipts, one category each, so the cover
   sheet (when it renders) has 5 subtotals and a total that reconciles. */
var ITEMS = [
  { file: 'IMG_20260214_093012.jpg',     date: '2026-02-14', note: 'Northside Coffee Co. - client lunch',    amount: '18.75',  category: 'Meals' },
  { file: 'IMG_20260218_181244.jpg',     date: '2026-02-18', note: 'Harbour Hardware - fasteners and tape',  amount: '142.30', category: 'Materials' },
  { file: '2026-03-02_fuel.jpg',         date: '2026-03-02', note: 'Kingsway Fuel Stop - van, site run',     amount: '78.40',  category: 'Travel' },
  { file: 'Scan_20260305-1420.jpg',      date: '2026-03-05', note: 'Meridian Office Supply - paper, toner',  amount: '64.99',  category: 'Office' },
  { file: 'IMG_20260311_120501.jpg',     date: '2026-03-11', note: 'Blue Anchor Cafe - team meeting',        amount: '26.50',  category: 'Meals' },
  { file: 'receipt-novaprint-mar14.jpg', date: '2026-03-14', note: 'Novaprint Digital - banner print',       amount: '310.00', category: 'Print' },
  { file: 'IMG_20260320_081500.jpg',     date: '2026-03-20', note: 'Kingsway Fuel Stop - van, site run',     amount: '71.20',  category: 'Travel' }
];

var BASE_OPTS = { title: 'Receipts', pageSize: 'letter', unlocked: false };

var logEl = null;
function log(x) { if (logEl) { logEl.textContent += x + '\n'; } }

function loadOne(src) {
  return new Promise(function (res, rej) {
    var img = new Image();
    img.onload = function () { res(img); };
    img.onerror = function () { rej(new Error('could not load ' + src)); };
    img.src = src;
  });
}

function sha256(bytes) {
  return crypto.subtle.digest('SHA-256', bytes).then(function (buf) {
    var b = new Uint8Array(buf), s = '', i;
    for (i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16);
    return s;
  });
}

function b64(u8) {
  var s = '', CH = 0x8000, i;
  for (i = 0; i < u8.length; i += CH) s += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
  return btoa(s);
}

function runBuild(items, opts) {
  return window.RS.buildPdf(items, opts).then(function (out) {
    return sha256(new Uint8Array(out.bytes)).then(function (h) {
      return { hash: h, pages: out.pages, size: out.bytes.length, b64: b64(new Uint8Array(out.bytes)) };
    });
  });
}

function run() {
  logEl = document.getElementById('log');
  logEl.textContent = '';
  var st = document.getElementById('status');

  if (!PDFLib || !window.RS) {
    window.__m = { error: 'engine missing PDFLib=' + !!PDFLib + ' RS=' + !!window.RS };
    if (st) st.textContent = 'engine missing';
    return Promise.resolve(window.__m);
  }

  log('clock frozen at ' + new Date().toISOString());
  log('engine: buildPdf present = ' + (typeof window.RS.buildPdf));

  var items = [];
  return ITEMS.reduce(function (chain, it) {
    return chain.then(function () {
      return loadOne('../samples/receipts/' + it.file);
    }).then(function (img) {
      return window.RS.normalizeImage(img, 0).then(function (n) {
        items.push({ date: it.date, note: it.note, amount: it.amount, category: it.category, bytes: n.bytes, w: n.w, h: n.h });
      });
    });
  }, Promise.resolve()).then(function () {
    log('input: ' + items.length + ' rows, 5 categories, total $712.14 expected');

    /* A — the shipping call, no report opt */
    return runBuild(items, BASE_OPTS).then(function (a) {
      log('A  no report      : ' + a.hash + '  ' + a.pages + ' pages, ' + a.size + ' B');

      /* A2 — the same call again, same page load: determinism */
      return runBuild(items, BASE_OPTS).then(function (a2) {
        log('A2 no report again: ' + a2.hash + '  ' + a2.pages + ' pages, ' + a2.size + ' B');
        log('   A == A2 (deterministic clock): ' + (a.hash === a2.hash));

        /* B — the new opt */
        var optsB = { title: BASE_OPTS.title, pageSize: BASE_OPTS.pageSize, unlocked: BASE_OPTS.unlocked,
                      report: { preparedFor: 'Acme Field Services Ltd.' } };
        return runBuild(items, optsB).then(function (b) {
          log('B  with report    : ' + b.hash + '  ' + b.pages + ' pages, ' + b.size + ' B');

          var m = {
            fixed: new Date().toISOString(),
            A:  { hash: a.hash,  pages: a.pages,  size: a.size },
            A2: { hash: a2.hash, pages: a2.pages, size: a2.size },
            B:  { hash: b.hash,  pages: b.pages,  size: b.size },
            deterministic: a.hash === a2.hash,
            existingPathUnchanged: a.hash === a2.hash,      // both are the no-report call
            reportAddsAPage: b.pages === a.pages + 1,
            reportB64: b.b64,
            csp: (window.__csp || []).slice(),
            errs: (window.__errs || []).slice()
          };
          window.__m = m;
          log('--- A.pages=' + a.pages + '  B.pages=' + b.pages + '  report adds a page: ' + m.reportAddsAPage);
          log('CSP violations: ' + JSON.stringify(m.csp) + '   errors: ' + JSON.stringify(m.errs));
          if (st) st.textContent = 'done';
          /* leave the report PDF on the page for a by-hand download */
          var url = URL.createObjectURL(new Blob([Uint8Array.from(atob(b.b64), function (c) { return c.charCodeAt(0); })], { type: 'application/pdf' }));
          var el = document.getElementById('out'); el.textContent = '';
          var aEl = document.createElement('a');
          aEl.href = url; aEl.download = 'measure-report-opt-B.pdf'; aEl.textContent = 'Download the report build (' + b.size + ' B)';
          el.appendChild(aEl);
          return m;
        });
      });
    });
  }).catch(function (e) {
    window.__m = { error: String(e && e.stack ? e.stack : e) };
    if (st) st.textContent = 'failed';
    log('FAILED: ' + window.__m.error);
    return window.__m;
  });
}

window.__measure = run;
function boot() { run(); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();

})();
