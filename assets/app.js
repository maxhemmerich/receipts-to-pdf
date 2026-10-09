/* ReceiptStack — the whole tool.
   Runs in the tab. No fetch, no upload, no key. See index.html for the CSP that enforces it. */
(function () {
'use strict';

/* ============================================================================
   SITE CONFIG lives in config.js, which index.html loads BEFORE this file.
   Fill CHECKOUT_URL there to turn the buy button live, and put the code a
   buyer is given into UNLOCK_CODE. Read them here with safe fallbacks, so a
   missing config.js degrades to the honest empty state instead of throwing.
   ============================================================================ */
var FREE_LIMIT   = 5;    // receipts per PDF on the free tier
var checkoutUrl = (typeof CHECKOUT_URL === 'string') ? CHECKOUT_URL.trim() : '';
var unlockCode  = (typeof UNLOCK_CODE  === 'string') ? UNLOCK_CODE.trim()  : '';
var priceUsd    = (typeof PRICE_USD === 'number' && isFinite(PRICE_USD)) ? PRICE_USD : 9;
/* ========================================================================== */

var LS_KEY = 'receiptstack.unlocked';
var PDFLib = window.PDFLib;

/* ---------------------------------------------------------------- helpers */

function money(n) {
  var neg = n < 0, v = Math.abs(n).toFixed(2).split('.');
  return (neg ? '-' : '') + '$' + v[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + v[1];
}

function bytesHuman(b) {
  if (b < 1024) return b + ' B';
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}

/* ------------------------------------------------------------- the unlock
   CHECKOUT_URL, UNLOCK_CODE and PRICE_USD come from config.js, which is
   public. UNLOCK_CODE therefore holds a DIGEST of the buyer's code, never the
   code itself: publishing the code would make the unlock free for everyone.

   The page derives PBKDF2-HMAC-SHA256(code, UNLOCK_SALT, UNLOCK_ITER, 32 bytes)
   and compares it with UNLOCK_CODE. Nothing leaves the browser — this works
   under connect-src 'none' — so the privacy promise on the page stays literal.

   Two rules the digest depends on, both stated in PAYMENT.md:
     - the code must be high entropy (>= 20 random characters). A short or
       guessable code does not matter to the page, but the digest is public, so
       a weak code is brute-forced offline and the unlock becomes free.
     - UNLOCK_SALT and UNLOCK_ITER are part of the contract. Changing either
       invalidates every code already issued.
   Mint a code with tools/mint-unlock-code.py; it prints the code and the digest. */
var UNLOCK_SALT = 'receiptstack.unlock.v1';
var UNLOCK_ITER = 210000;

function digestHex(code) {
  var subtle = (window.crypto && window.crypto.subtle) || null;
  if (!subtle) return Promise.reject(new Error('no WebCrypto'));
  var enc = new TextEncoder();
  var normalized = String(code).replace(/[\s-]+/g, '').toUpperCase();
  return subtle.importKey('raw', enc.encode(normalized), 'PBKDF2', false, ['deriveBits'])
    .then(function (key) {
      return subtle.deriveBits(
        { name: 'PBKDF2', salt: enc.encode(UNLOCK_SALT), iterations: UNLOCK_ITER, hash: 'SHA-256' },
        key, 256);
    })
    .then(function (bits) {
      var b = new Uint8Array(bits), s = '', i;
      for (i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16);
      return s;
    });
}

/* Length-checked, no early exit on the first differing character. */
function sameHex(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  var diff = 0, i;
  for (i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function slug(s) {
  return String(s || 'receipts').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'receipts';
}

/* pdf-lib's standard fonts are WinAnsi. Anything the font cannot encode throws,
   so map typographic characters down and replace the rest. */
var SUBST = {
  '\u2018': "'", '\u2019': "'", '\u201A': "'", '\u201B': "'",
  '\u201C': '"', '\u201D': '"', '\u201E': '"', '\u201F': '"',
  '\u2013': '-', '\u2014': '-', '\u2212': '-', '\u2010': '-', '\u2011': '-',
  '\u2026': '...', '\u2022': '-', '\u00B7': '-', '\u2032': "'", '\u2033': '"',
  '\u00A0': ' ', '\u202F': ' ', '\u2009': ' ', '\u200B': ''
};

function clean(s) {
  s = String(s === undefined || s === null ? '' : s);
  var out = '', i, c, ch;
  for (i = 0; i < s.length; i++) {
    ch = s.charAt(i);
    if (Object.prototype.hasOwnProperty.call(SUBST, ch)) { out += SUBST[ch]; continue; }
    c = s.charCodeAt(i);
    if (c === 9) { out += ' '; continue; }
    if (c < 32) continue;
    if (c >= 0xDC00 && c <= 0xDFFF) continue;              // low half of a surrogate pair already replaced
    if (c <= 0x7E) { out += ch; continue; }
    if (c >= 0xA0 && c <= 0xFF) { out += ch; continue; }   // Latin-1 half of WinAnsi
    if (c === 0x85) { out += '...'; continue; }
    out += '?';                                            // emoji, CJK, anything else
  }
  return out;
}

/* Width of a string in a standard font, so columns line up. */
function w(text, font, size) {
  try { return font.widthOfTextAtSize(clean(text), size); } catch (e) { return 0; }
}

function fit(text, font, size, max) {
  var t = clean(text);
  if (w(t, font, size) <= max) return t;
  while (t.length > 1 && w(t + '...', font, size) > max) t = t.slice(0, -1);
  return t + '...';
}

/* ------------------------------------------------------- date from a name */

var MONS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

function ymd(y, m, d) {
  if (!(m >= 1 && m <= 12) || !(d >= 1 && d <= 31)) return null;
  var dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
}

/* Reads the date out of a filename. Deliberately conservative: it only returns a
   date it cannot get wrong. Anything ambiguous (03/04/2026) returns null and is
   left for you to fill in. */
function parseDateFromName(name) {
  var base = String(name || '').replace(/\.[a-z0-9]{1,5}$/i, '');
  var m, r;

  // 2026-03-02, 2026_03_02, 2026.03.02
  m = base.match(/(19\d{2}|20\d{2})[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])(?!\d)/);
  if (m) { r = ymd(+m[1], +m[2], +m[3]); if (r) return r; }

  // 20260302
  m = base.match(/(19\d{2}|20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)/);
  if (m) { r = ymd(+m[1], +m[2], +m[3]); if (r) return r; }

  // 2 Mar 2026 / 02March2026
  m = base.match(/(0?[1-9]|[12]\d|3[01])[\s\-_.]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-_.]*(19\d{2}|20\d{2})/i);
  if (m) { r = ymd(+m[3], MONS[m[2].toLowerCase()], +m[1]); if (r) return r; }

  // Mar 2 2026 / mar-02-2026
  m = base.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-_.]*(0?[1-9]|[12]\d|3[01])[\s\-_.]*(19\d{2}|20\d{2})/i);
  if (m) { r = ymd(+m[3], MONS[m[1].toLowerCase()], +m[2]); if (r) return r; }

  return null;
}

/* --------------------------------------------------------------- the CSV
   The index rows, as a file. Same rows the PDF cover index prints, same order,
   same total — one line per receipt, then the total line. Amounts are written
   as plain numbers (18.75, not $18.75) so a spreadsheet reads them as numbers
   and a blank amount stays an empty cell. A UTF-8 BOM leads the file so Excel
   opens the non-ASCII characters correctly. */

function csvCell(v) {
  var s = String(v === undefined || v === null ? '' : v);
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function amountOf(it) {
  var n = parseFloat(String(it.amount).replace(/[^0-9.\-]/g, ''));
  return isFinite(n) ? n : null;
}

function csvFor(items) {
  var amts = items.map(amountOf);
  var entered = amts.filter(function (a) { return a !== null; }).length;
  var total = amts.reduce(function (a, b) { return a + (b === null ? 0 : b); }, 0);
  var label = entered === 0 ? 'Total'
    : entered === amts.length ? 'Total of ' + entered + (entered === 1 ? ' amount' : ' amounts')
    : 'Total of ' + entered + ' of ' + amts.length + ' amounts';

  var rows = [['No', 'Date', 'Note', 'Amount']];
  items.forEach(function (it, i) {
    rows.push([String(i + 1), it.date || '', it.note || '',
               amts[i] === null ? '' : amts[i].toFixed(2)]);
  });
  rows.push(['', '', label, entered === 0 ? '' : total.toFixed(2)]);

  return '\uFEFF' + rows.map(function (r) {
    return r.map(csvCell).join(',');
  }).join('\r\n') + '\r\n';
}

/* ------------------------------------------------- report categories
   Groups the items for the expense-report cover sheet, in first-appearance
   order, with a per-category subtotal. A row with no category lands in one
   'Uncategorised' group. Only used when opts.report is passed. */
function reportGroups(items) {
  var order = [], map = {};
  items.forEach(function (it) {
    var c = String(it.category === undefined || it.category === null ? '' : it.category).trim() || 'Uncategorised';
    if (!map[c]) { map[c] = { cat: c, rows: [], sub: 0 }; order.push(c); }
    map[c].rows.push(it);
    var n = amountOf(it);
    if (n !== null) map[c].sub += n;
  });
  return order.map(function (c) { return map[c]; });
}

/* ------------------------------------------------------------- image work */

function loadImg(src) {
  return new Promise(function (res, rej) {
    var img = new Image();
    if (typeof src === 'string') {
      img.onload = function () { res(img); };
      img.onerror = function () { rej(new Error('could not load image')); };
      img.src = src;
    } else {
      var url = URL.createObjectURL(src);
      img.onload = function () { URL.revokeObjectURL(url); res(img); };
      img.onerror = function () { URL.revokeObjectURL(url); rej(new Error('not an image this browser can read')); };
      img.src = url;
    }
  });
}

var MAX_EDGE = 2200, JPG_Q = 0.92;

/* Bakes EXIF orientation, manual rotation and a size cap into one JPEG.
   Returns the exact bytes that go into the PDF. */
function normalizeImage(img, rotationDeg) {
  var rot = ((rotationDeg || 0) % 360 + 360) % 360;
  var nw = img.naturalWidth || img.width, nh = img.naturalHeight || img.height;
  if (!nw || !nh) return Promise.reject(new Error('image has no pixels'));
  var scale = Math.min(1, MAX_EDGE / Math.max(nw, nh));
  var cw = Math.max(1, Math.round(nw * scale)), ch = Math.max(1, Math.round(nh * scale));
  var swap = (rot === 90 || rot === 270);
  var canvas = document.createElement('canvas');
  canvas.width = swap ? ch : cw;
  canvas.height = swap ? cw : ch;
  var ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.rotate(rot * Math.PI / 180);
  ctx.drawImage(img, -cw / 2, -ch / 2, cw, ch);
  ctx.restore();
  return new Promise(function (res, rej) {
    canvas.toBlob(function (blob) {
      if (!blob) { rej(new Error('could not re-encode image')); return; }
      blob.arrayBuffer().then(function (buf) {
        res({ bytes: new Uint8Array(buf), w: canvas.width, h: canvas.height });
      }, rej);
    }, 'image/jpeg', JPG_Q);
  });
}

/* --------------------------------------------------------------- the PDF */

var GREY = [0.42, 0.40, 0.35], INK = [0.10, 0.09, 0.08], RULE = [0.85, 0.82, 0.75];

function rgb(c) { return PDFLib.rgb(c[0], c[1], c[2]); }

function buildPdf(items, opts) {
  var doc, font, bold, PW, PH, M, FOOT, i, j;
  var created = new Date();
  var unlocked = !!opts.unlocked;
  var mark = !unlocked;
  /* ADDITIVE (NEXT.md #8). Absent -> this is null and every line below draws
     exactly what it drew before; present -> one expense-report cover sheet is
     inserted as page 1 and nothing else moves. */
  var report = (opts && opts.report) ? opts.report : null;

  return PDFLib.PDFDocument.create().then(function (d) {
    doc = d;
    doc.setTitle(clean(opts.title || 'Receipts'));
    doc.setAuthor('ReceiptStack');
    doc.setSubject('Receipts, one page each, in date order');
    doc.setProducer('ReceiptStack (browser)');
    doc.setCreator('ReceiptStack (browser)');
    doc.setCreationDate(created);
    doc.setModificationDate(created);
    return Promise.all([doc.embedFont(PDFLib.StandardFonts.Helvetica),
                        doc.embedFont(PDFLib.StandardFonts.HelveticaBold)]);
  }).then(function (fonts) {
    font = fonts[0]; bold = fonts[1];
    if (opts.pageSize === 'a4') { PW = 595.28; PH = 841.89; } else { PW = 612; PH = 792; }
    M = 36; FOOT = 26;

    /* ---- amounts up front ---- */
    var amts = items.map(function (it) {
      var n = parseFloat(String(it.amount).replace(/[^0-9.\-]/g, ''));
      return isFinite(n) ? n : null;
    });
    var total = amts.reduce(function (a, b) { return a + (b === null ? 0 : b); }, 0);
    var dated = items.filter(function (it) { return it.date; }).map(function (it) { return it.date; }).sort();
    var period = dated.length ? (dated[0] + ' to ' + dated[dated.length - 1]) : 'dates not set';

    /* ---- cover / index page ---- */
    var top = PH - M, y = top;
    doc.getPages();
    var page = doc.addPage([PW, PH]);
    function line(yy, col, thick) {
      page.drawRectangle({ x: M, y: yy, width: PW - 2 * M, height: thick || 0.7, color: rgb(col || RULE) });
    }
    function at(text, x, yy, f, size, col) {
      page.drawText(clean(text), { x: x, y: yy, size: size, font: f || font, color: rgb(col || INK) });
    }
    function atRight(text, xr, yy, f, size, col) {
      var t = clean(text);
      page.drawText(t, { x: xr - (f || font).widthOfTextAtSize(t, size), y: yy, size: size, font: f || font, color: rgb(col || INK) });
    }

    y = top - 8;
    at('ReceiptStack', M, y, bold, 9, GREY);
    atRight(created.toISOString().slice(0, 10), PW - M, y, font, 9, GREY);
    y -= 26;
    at(fit(opts.title || 'Receipts', bold, 24, PW - 2 * M), M, y, bold, 24);
    y -= 20;
    at(clean(items.length + (items.length === 1 ? ' receipt' : ' receipts') + '  \u00b7  ' + period), M, y, font, 10.5, GREY);
    y -= 22;
    line(y, INK, 1.2);
    y -= 22;

    // column x positions
    var cNo = M, cDate = M + 26, cNote = M + 112, cAmt = PW - M;

    function header(yy) {
      at('No', cNo, yy, bold, 8, GREY);
      at('Date', cDate, yy, bold, 8, GREY);
      at('Note', cNote, yy, bold, 8, GREY);
      atRight('Amount', cAmt, yy, bold, 8, GREY);
      line(yy - 6, RULE, 0.7);
    }

    header(y);
    y -= 24;

    var rowH = 16;
    var floorY = M + FOOT + 34;

    for (i = 0; i < items.length; i++) {
      if (y < floorY) {
        page = doc.addPage([PW, PH]);
        y = top - 8;
        at('Receipt index, continued', M, y, bold, 9, GREY);
        y -= 22;
        header(y);
        y -= 24;
      }
      at(String(i + 1), cNo, y, font, 10);
      at(items[i].date || '-', cDate, y, font, 10, items[i].date ? INK : GREY);
      at(fit(items[i].note || '', font, 10, cNote - cDate - 0), cNote, y, font, 10);
      atRight(amts[i] === null ? '-' : money(amts[i]), cAmt, y, font, 10);
      y -= rowH;
    }

    // keep the total with at least a couple of rows above it
    if (y < M + FOOT + 44) {
      page = doc.addPage([PW, PH]);
      y = top - 8;
      at('Receipt index, continued', M, y, bold, 9, GREY);
      y -= 34;
    }
    y -= 4;
    line(y + 12, INK, 1);
    var entered = amts.filter(function (a) { return a !== null; }).length;
    var label = entered === 0 ? 'Total'
      : entered === amts.length ? 'Total of ' + entered + (entered === 1 ? ' amount' : ' amounts')
      : 'Total of ' + entered + ' of ' + amts.length + ' amounts';
    at(label, cNote, y, bold, 10);
    if (entered === 0) {
      atRight('no amounts entered', cAmt, y, font, 9.5, GREY);
    } else {
      atRight(money(total), cAmt, y, bold, 11);
    }

    at('Every receipt is on its own page after this one, in the order listed.', M, M + FOOT + 8, font, 8.5, GREY);

    /* ---- optional expense-report cover sheet (NEXT.md #8) ----
       Only ever drawn when opts.report was passed. It reuses this document's
       own embedded fonts, page size, margin and type scale, and is inserted as
       page 1, ahead of the index page drawn above — so with no `report` opt
       nothing here runs and the bytes are exactly what they were. */
    function drawReportCover() {
      var pg = doc.insertPage(0, [PW, PH]);
      var top2 = PH - M, yy = top2;
      var cDate = M + 18, cCat = M + 86, cNote = M + 186, cAmt = PW - M;
      var pf = String(report.preparedFor === undefined || report.preparedFor === null ? '' : report.preparedFor).trim();

      function line(y2, col, thick, x, width) {
        pg.drawRectangle({ x: (x === undefined ? M : x), y: y2,
          width: (width === undefined ? PW - 2 * M : width),
          height: thick || 0.7, color: rgb(col || RULE) });
      }
      function at2(text, x, y2, f, size, col) {
        pg.drawText(clean(text), { x: x, y: y2, size: size, font: f || font, color: rgb(col || INK) });
      }
      function atRight2(text, xr, y2, f, size, col) {
        var t = clean(text);
        pg.drawText(t, { x: xr - (f || font).widthOfTextAtSize(t, size), y: y2, size: size, font: f || font, color: rgb(col || INK) });
      }

      yy = top2 - 8;
      at2('ReceiptStack', M, yy, bold, 9, GREY);
      atRight2(created.toISOString().slice(0, 10), PW - M, yy, font, 9, GREY);
      yy -= 26;
      at2(fit(opts.title || 'Receipts', bold, 24, PW - 2 * M), M, yy, bold, 24);
      yy -= 20;
      var sub = 'Prepared for ' + (pf || '-') + '  \u00b7  ' + period + '  \u00b7  ' +
                items.length + (items.length === 1 ? ' expense' : ' expenses');
      at2(fit(sub, font, 10.5, PW - 2 * M), M, yy, font, 10.5, GREY);
      yy -= 22;
      line(yy, INK, 1.2);
      yy -= 22;

      at2('Date', cDate, yy, bold, 8, GREY);
      at2('Category', cCat, yy, bold, 8, GREY);
      at2('Note', cNote, yy, bold, 8, GREY);
      atRight2('Amount', cAmt, yy, bold, 8, GREY);
      line(yy - 6, RULE, 0.7);
      yy -= 24;

      var rowH2 = 16, groups = reportGroups(items), floorY2 = M + 150, spilled = 0;

      groups.forEach(function (g) {
        g.rows.forEach(function (it) {
          if (yy < floorY2) { spilled++; return; }
          at2(it.date || '-', cDate, yy, font, 10, it.date ? INK : GREY);
          at2(fit(g.cat, font, 10, cNote - cCat - 8), cCat, yy, font, 10);
          at2(fit(it.note || '', font, 10, cAmt - cNote - 8), cNote, yy, font, 10);
          var n = amountOf(it);
          atRight2(n === null ? '-' : money(n), cAmt, yy, font, 10);
          yy -= rowH2;
        });
        if (spilled) return;
        yy -= 2;
        at2('Subtotal \u00b7 ' + g.cat, cCat, yy, bold, 9, GREY);
        atRight2(money(g.sub), cAmt, yy, bold, 9);
        yy -= 8;
        line(yy, RULE, 0.5, cCat, cAmt - cCat);
        yy -= 12;
      });

      if (spilled) {
        at2(spilled + ' row' + (spilled === 1 ? '' : 's') + ' did not fit on this page', cCat, yy, font, 9, GREY);
        yy -= rowH2;
      }

      yy -= 2;
      line(yy + 12, INK, 1);
      at2(label, cNote, yy, bold, 10);
      if (entered === 0) atRight2('no amounts entered', cAmt, yy, font, 9.5, GREY);
      else atRight2(money(total), cAmt, yy, bold, 11);

      var sigY = M + 96, sigW = 210, gap = 26;
      [
        { x: M, lbl: 'Signature' },
        { x: M + sigW + gap, w: 130, lbl: 'Date' },
        { x: M + sigW + gap + 156, w: PW - M - (M + sigW + gap + 156), lbl: 'Approved by (name)' }
      ].forEach(function (sg) {
        line(sigY, RULE, 0.7, sg.x, sg.w === undefined ? sigW : sg.w);
        at2(sg.lbl, sg.x, sigY - 12, font, 8.5, GREY);
      });

      at2('Every receipt is on its own page after this one, in the order listed.', M, M + FOOT + 8, font, 8.5, GREY);
    }

    /* ---- one page per receipt ---- */
    var iw = PW - 2 * M, ih = PH - M - FOOT - M - 10;

    return items.reduce(function (chain, it, k) {
      return chain.then(function () {
        return doc.embedJpg(it.bytes);
      }).then(function (img) {
        var p = doc.addPage([PW, PH]);
        var scale = Math.min(iw / img.width, ih / img.height);
        var dw = img.width * scale, dh = img.height * scale;
        var dx = (PW - dw) / 2, dy = M + FOOT + 10 + (ih - dh) / 2;
        p.drawRectangle({ x: dx, y: dy, width: dw, height: dh, color: rgb([1, 1, 1]) });
        p.drawImage(img, { x: dx, y: dy, width: dw, height: dh });
        p.drawRectangle({ x: dx, y: dy, width: dw, height: dh, borderColor: rgb(RULE), borderWidth: 0.7 });

        var footY = M + 8;
        p.drawText(clean('Receipt ' + (k + 1) + ' of ' + items.length), { x: M, y: footY, size: 8.5, font: font, color: rgb(GREY) });
        var mid = (it.date ? it.date : 'no date') + (amts[k] === null ? '' : '  \u00b7  ' + money(amts[k]));
        var mt = clean(mid);
        p.drawText(mt, { x: (PW - font.widthOfTextAtSize(mt, 8.5)) / 2, y: footY, size: 8.5, font: font, color: rgb(GREY) });
        if (mark) {
          var mr = clean('Made with ReceiptStack \u2014 free version');
          p.drawText(mr, { x: PW - M - font.widthOfTextAtSize(mr, 8.5), y: footY, size: 8.5, font: font, color: rgb(GREY) });
        }
        if (it.note) {
          p.drawText(fit(it.note, font, 9.5, PW - 2 * M), { x: M, y: PH - M + 4, size: 9.5, font: font, color: rgb(GREY) });
        }
      });
    }, Promise.resolve()).then(function () {
      if (report) drawReportCover();
      return doc.save({ useObjectStreams: false });
    }).then(function (out) {
      return { bytes: out, pages: doc.getPageCount() };
    });
  });
}

/* ------------------------------------------------------------------- UI */

var $ = function (id) { return document.getElementById(id); };

var state = { items: [], unlocked: false, nextId: 1, reading: 0, building: false };

try { state.unlocked = localStorage.getItem(LS_KEY) === '1'; } catch (e) {}
if (!unlockCode) state.unlocked = false;

var SAMPLES = [
  { file: 'IMG_20260214_093012.jpg',    note: 'Northside Coffee Co.',    amount: '18.75' },
  { file: 'IMG_20260218_181244.jpg',    note: 'Harbour Hardware',        amount: '142.30' },
  { file: '2026-03-02_fuel.jpg',        note: 'Kingsway Fuel Stop',      amount: '78.40' },
  { file: 'Scan_20260305-1420.jpg',     note: 'Meridian Office Supply',  amount: '64.99' },
  { file: 'IMG_20260311_120501.jpg',    note: 'Blue Anchor Cafe',        amount: '26.50' },
  { file: 'receipt-novaprint-mar14.jpg', note: 'Novaprint Digital',      amount: '310.00', date: '2026-03-14' },
  { file: 'IMG_20260320_081500.jpg',    note: 'Kingsway Fuel Stop',      amount: '71.20' }
];

function setStatus(msg, isErr) {
  var el = $('status');
  el.textContent = msg || '';
  el.className = 'status' + (isErr ? ' err' : '');
}

/* The Build button stays inert until every photo in the current drop has
   finished decoding, so no count is ever taken from a half-read list. */
function updateControls() {
  var busy = state.reading > 0 || state.building;
  var b = $('buildBtn'), s = $('sampleBtn');
  if (b) b.disabled = busy;
  if (s) s.disabled = state.reading > 0;
}
function beginRead() {
  state.reading++;
  $('result').hidden = true;   // a stale result can never sit next to a changing list
  updateControls();
}
function endRead() {
  state.reading = Math.max(0, state.reading - 1);
  updateControls();
}

/* The checkout slot. It is ATOMIC: a live buy link is rendered only when BOTH a
   checkout URL and a digest are present, so the page can never take money for an
   unlock it cannot deliver. If one half is set and the other is missing, the
   control stays the honest disabled button and the note names the missing half.
   The code box is visible exactly when a digest exists — which is exactly when a
   code could work — so a live buy link always ships with its code box. (Both
   halves can be pasted in one step, but the page no longer depends on that: a
   half-wired checkout reads "not ready", never a $9 link with no box.) */
function renderBuy() {
  var slot = $('buySlot'), note = $('buyNote'), row = $('unlockRow');
  if (!slot) return;
  var haveUrl  = !!checkoutUrl;
  var haveCode = !!unlockCode;   // holds the digest, never the code itself
  slot.textContent = '';
  if (state.unlocked) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'primary'; b.disabled = true;
    b.textContent = 'Unlocked on this browser';
    slot.appendChild(b);
    if (note) note.textContent = 'The receipt limit and the footer mark are off. This is stored in this browser only.';
  } else if (haveUrl && haveCode) {
    var a = document.createElement('a');
    a.className = 'primary';
    a.href = checkoutUrl;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'Unlock \u2014 $' + priceUsd + ' once';
    slot.appendChild(a);
    if (note) note.textContent = 'One payment, no subscription. The code arrives on the checkout page.';
  } else {
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'primary'; btn.disabled = true;
    if (haveUrl && !haveCode) {
      // checkout wired, but no code has been issued: a purchase would take the
      // money and hand the buyer nothing to unlock with.
      btn.textContent = "Unlock code isn't set up yet";
      if (note) note.textContent = 'The checkout is connected, but no unlock code exists yet, so a purchase right ' +
        'now would take your money and give you nothing to unlock with. Nothing is for sale on this page until ' +
        'that is fixed. The free version works fully for up to ' + FREE_LIMIT + ' receipts.';
    } else if (!haveUrl && haveCode) {
      // the unlock is ready but there is nowhere to buy it.
      btn.textContent = "Checkout isn't connected yet";
      if (note) note.textContent = 'An unlock code is ready, but there is no checkout connected yet, so there is ' +
        'nothing to buy. The free version works fully for up to ' + FREE_LIMIT + ' receipts.';
    } else {
      btn.textContent = "Checkout isn't connected yet";
      if (note) note.textContent = 'Nothing is for sale on this page right now. The free version works fully for ' +
        'up to ' + FREE_LIMIT + ' receipts. When checkout is connected, a code arrives with your purchase and goes ' +
        'in the box below.';
    }
    slot.appendChild(btn);
  }
  if (row) row.hidden = !haveCode;   // the code box exists iff a digest exists
}

function capInfo() {
  var shown = state.unlocked ? state.items.length : Math.min(state.items.length, FREE_LIMIT);
  return { shown: shown, over: Math.max(0, state.items.length - shown) };
}

function renderCap() {
  var note = $('capNote'), info = capInfo();
  if (info.over > 0) {
    note.hidden = false;
    note.innerHTML = 'Free version: only the first <b>' + FREE_LIMIT + ' of ' + state.items.length +
      '</b> receipts will go into the PDF. <a href="#price">Unlock</a> to include all of them.';
  } else {
    note.hidden = true;
  }
  $('limitLine').hidden = state.unlocked;
}

function renderList() {
  var list = $('list');
  list.textContent = '';
  state.items.forEach(function (it, idx) {
    var li = document.createElement('li');
    li.className = 'row';

    var thumb = document.createElement('img');
    thumb.src = it.thumb;
    thumb.alt = '';
    li.appendChild(thumb);

    var meta = document.createElement('div');
    meta.className = 'meta';

    var who = document.createElement('div');
    who.className = 'fname';
    who.textContent = it.name;
    meta.appendChild(who);

    var inputs = document.createElement('div');
    inputs.className = 'l1';

    var note = document.createElement('input');
    note.type = 'text'; note.className = 'note-in'; note.placeholder = 'Note (e.g. client lunch)';
    note.value = it.note; note.maxLength = 80;
    note.addEventListener('input', function () { it.note = note.value; });
    inputs.appendChild(note);

    var cat = document.createElement('input');
    cat.type = 'text'; cat.className = 'cat-in'; cat.placeholder = 'Category';
    cat.value = it.category || ''; cat.maxLength = 40;
    cat.title = 'Category, used by the expense-report cover sheet';
    cat.addEventListener('input', function () { it.category = cat.value; });
    inputs.appendChild(cat);

    var acts = document.createElement('div');
    acts.className = 'acts';
    [['\u25B2', 'up', -1], ['\u25BC', 'down', 1]].forEach(function (spec) {
      var b = document.createElement('button');
      b.type = 'button'; b.textContent = spec[0]; b.title = 'move ' + spec[1];
      b.addEventListener('click', function () {
        var t = idx + spec[2];
        if (t < 0 || t >= state.items.length) return;
        var tmp = state.items[idx]; state.items[idx] = state.items[t]; state.items[t] = tmp;
        renderList();
      });
      acts.appendChild(b);
    });
    var rot = document.createElement('button');
    rot.type = 'button'; rot.textContent = '\u21BB'; rot.title = 'rotate 90 degrees';
    rot.addEventListener('click', function () { rotate(idx); });
    acts.appendChild(rot);
    var rm = document.createElement('button');
    rm.type = 'button'; rm.className = 'rm'; rm.textContent = '\u00D7'; rm.title = 'remove';
    rm.addEventListener('click', function () {
      state.items.splice(idx, 1);
      renderList(); renderCap();
    });
    acts.appendChild(rm);
    inputs.appendChild(acts);
    meta.appendChild(inputs);

    var l2 = document.createElement('div');
    l2.className = 'l2';

    var date = document.createElement('input');
    date.type = 'date'; date.className = 'date-in';
    date.value = it.date || '';

    var amt = document.createElement('input');
    amt.type = 'text'; amt.inputMode = 'decimal'; amt.className = 'amt-in'; amt.placeholder = '0.00';
    amt.value = it.amount;
    amt.addEventListener('input', function () { it.amount = amt.value; });

    var g = document.createElement('div');
    g.className = 'date-guess' + (it.dateSource === 'name' ? '' : ' manual');

    function label() {
      g.className = 'date-guess' + (it.dateSource === 'name' ? '' : ' manual');
      g.textContent =
        it.dateSource === 'name' ? 'date read from the filename' :
        it.dateSource === 'given' ? 'date from the sample data' :
        it.dateSource === 'manual' ? 'date set by hand' :
        'no date in the filename \u2014 set it';
    }
    label();

    date.addEventListener('input', function () {
      it.date = date.value;
      if (date.value) it.dateSource = 'manual';
      label();
    });

    l2.appendChild(date); l2.appendChild(amt); l2.appendChild(g);
    meta.appendChild(l2);

    li.appendChild(meta);
    list.appendChild(li);
  });
  $('controls').hidden = state.items.length === 0;
  renderCap();
}

function thumbFor(img) {
  var c = document.createElement('canvas');
  var s = 92 / Math.max(img.width, img.height);
  c.width = Math.max(1, Math.round(img.width * s));
  c.height = Math.max(1, Math.round(img.height * s));
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.6);
}

/* A drop is one batch. The page promises the PDF "in date order", and the file
   picker hands its files over in whatever order the dialog shows them, so the
   batch is put in date order here, oldest first, instead of in drop order.
   Anything with no date keeps its relative order and sits after the dated
   ones. This runs on a batch add only: a date typed in by hand or a row moved
   with the arrows is never re-sorted out from under you. */
function sortByDate() {
  var wrapped = state.items.map(function (it, i) { return { it: it, i: i }; });
  wrapped.sort(function (a, b) {
    var na = a.it.date ? 0 : 1, nb = b.it.date ? 0 : 1;
    if (na !== nb) return na - nb;                       // dated first, undated last
    if (na === 0 && a.it.date !== b.it.date) return a.it.date < b.it.date ? -1 : 1;
    return a.i - b.i;                                    // stable within a group
  });
  state.items = wrapped.map(function (w) { return w.it; });
}

/* Adds one already-decoded image. Used by both the file picker and the loader. */
function addImage(img, name, preset) {
  preset = preset || {};
  var fromName = parseDateFromName(name);
  var date = preset.date || fromName;
  var it = {
    id: state.nextId++,
    name: name,
    img: img,
    rotation: 0,
    note: preset.note || '',
    amount: preset.amount || '',
    category: preset.category || '',
    date: date || '',
    dateSource: preset.date ? 'given' : (fromName ? 'name' : 'none'),
    thumb: thumbFor(img),
    bytes: null, w: 0, h: 0
  };
  state.items.push(it);
  return normalizeImage(img, 0).then(function (n) {
    it.bytes = n.bytes; it.w = n.w; it.h = n.h;
    return it;
  });
}

function addFiles(files) {
  var list = Array.prototype.slice.call(files || []);
  if (!list.length) return;
  beginRead();
  setStatus('Reading ' + list.length + (list.length === 1 ? ' photo' : ' photos') + '\u2026');
  var bad = [];
  return list.reduce(function (chain, f) {
    return chain.then(function () {
      if (!/^image\//.test(f.type) && !/\.(jpe?g|png|webp|gif|bmp)$/i.test(f.name)) {
        bad.push(f.name + ' (not an image)');
        return;
      }
      return loadImg(f).then(function (img) {
        return addImage(img, f.name);
      }).catch(function (e) {
        bad.push(f.name + ' (' + e.message + ')');
      });
    });
  }, Promise.resolve()).then(function () {
    sortByDate();
    renderList();
    setStatus(bad.length ? 'Skipped: ' + bad.join(', ') : '', bad.length > 0);
  }).then(endRead, endRead);
}

function rotate(idx) {
  var it = state.items[idx];
  it.rotation = (it.rotation + 90) % 360;
  return normalizeImage(it.img, it.rotation).then(function (n) {
    it.bytes = n.bytes; it.w = n.w; it.h = n.h;
    setStatus('Rotated to ' + it.rotation + ' degrees.');
  });
}

function loadSamples() {
  if (state.reading > 0 || state.building) return;   // one read at a time
  beginRead();
  setStatus('Loading the 7 sample receipts\u2026');
  var base = 'samples/receipts/';
  return SAMPLES.reduce(function (chain, s) {
    return chain.then(function () {
      return loadImg(base + s.file).then(function (img) {
        return addImage(img, s.file, s);
      }).catch(function (e) {
        setStatus('Could not load the samples: ' + e.message + ' (open the page over http://, not file://)', true);
      });
    });
  }, Promise.resolve()).then(function () { sortByDate(); renderList(); setStatus(''); }).then(endRead, endRead);
}

var lastPdfBlob = null, lastPdfUrl = null, lastCsvUrl = null, lastCsvText = '';

function build() {
  if (state.reading > 0 || state.building) return;    // never build from a half-read list
  var items = state.items.slice();                     // ONE snapshot for every limit number
  if (!items.length) { setStatus('Add at least one receipt photo first.', true); return; }
  var info = capInfo();
  var included = items.slice(0, info.shown);
  var totalItems = items.length;
  var missing = totalItems - included.length;

  state.building = true;
  updateControls();
  setStatus('Building ' + included.length + ' pages\u2026');

  var t0 = performance.now();
  var opts = {
    title: $('title').value || 'Receipts',
    pageSize: $('pageSize').value,
    unlocked: state.unlocked
  };
  /* expense-report mode: the SAME engine and the SAME unlock, one extra opt.
     It changes only what page 1 looks like — the free cap and the footer mark
     are applied by the lines above, before this, and are untouched here. */
  var modeEl = $('mode');
  if (modeEl && modeEl.value === 'report') {
    opts.report = { preparedFor: ($('preparedFor') ? $('preparedFor').value.trim() : '') };
  }
  buildPdf(included, opts).then(function (out) {
    var blob = new Blob([out.bytes], { type: 'application/pdf' });
    if (lastPdfUrl) URL.revokeObjectURL(lastPdfUrl);
    lastPdfBlob = blob;
    lastPdfUrl = URL.createObjectURL(blob);

    var dates = included.filter(function (i) { return i.date; }).map(function (i) { return i.date; }).sort();
    var range = dates.length ? dates[0] + '-to-' + dates[dates.length - 1] : 'no-dates';
    var fname = slug($('title').value || 'receipts') + '-' + range + '.pdf';

    /* the same rows as the cover index, as a spreadsheet file. Built from the
       SAME `included` slice as the PDF, so the free limit means the same thing
       in the CSV as it does in the file. */
    lastCsvText = csvFor(included);
    var csvBlob = new Blob([lastCsvText], { type: 'text/csv' });
    if (lastCsvUrl) URL.revokeObjectURL(lastCsvUrl);
    lastCsvUrl = URL.createObjectURL(csvBlob);
    var cname = slug($('title').value || 'receipts') + '-' + range + '.csv';

    var res = $('result');
    res.textContent = '';
    var p1 = document.createElement('p');
    p1.innerHTML = '<b>' + included.length + (included.length === 1 ? ' receipt' : ' receipts') + '</b> \u2192 ' +
      '<span class="nums">' + out.pages + '</span> page' + (out.pages === 1 ? '' : 's') +
      ', <span class="nums">' + bytesHuman(out.bytes.length) + '</span>, built in ' +
      '<span class="nums">' + ((performance.now() - t0) / 1000).toFixed(1) + 's</span> on this machine.';
    res.appendChild(p1);

    if (missing > 0) {
      var p2 = document.createElement('p');
      p2.innerHTML = '<b>' + missing + '</b> receipt' + (missing === 1 ? '' : 's') +
        ' left out by the free limit. <a href="#price">Unlock</a> to include ' +
        totalItems + '.';
      res.appendChild(p2);
    }

    var a = document.createElement('a');
    a.className = 'download';
    a.href = lastPdfUrl;
    a.download = fname;
    a.textContent = 'Download ' + fname;
    res.appendChild(a);

    var c = document.createElement('a');
    c.className = 'download secondary';
    c.href = lastCsvUrl;
    c.download = cname;
    c.textContent = 'Download ' + cname;
    res.appendChild(c);

    var hint = document.createElement('p');
    hint.className = 'dim';
    hint.textContent = 'The CSV is the same rows as the index page \u2014 one line per receipt ' +
      'plus the total \u2014 for a spreadsheet.';
    res.appendChild(hint);

    res.hidden = false;
    setStatus('Nothing was uploaded. The PDF and the CSV were made in this tab.');
    state.building = false;
    updateControls();
  }).catch(function (e) {
    setStatus('The PDF could not be built: ' + e.message, true);
    state.building = false;
    updateControls();
  });
}

/* ------------------------------------------------------------- wiring */

function init() {
  if (!PDFLib) { setStatus('pdf-lib did not load, so the tool cannot run.', true); return; }

  var drop = $('drop'), picker = $('picker');

  $('chooseBtn').addEventListener('click', function (e) { e.stopPropagation(); picker.click(); });
  drop.addEventListener('click', function () { picker.click(); });
  picker.addEventListener('change', function () { addFiles(picker.files); picker.value = ''; });

  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('hot'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('hot'); });
  });
  drop.addEventListener('drop', function (e) {
    if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
  });
  ['dragover', 'drop'].forEach(function (ev) {
    window.addEventListener(ev, function (e) { e.preventDefault(); });
  });

  $('sampleBtn').addEventListener('click', loadSamples);
  $('buildBtn').addEventListener('click', build);

  /* Mode: the expense-report cover sheet is a mode on the SAME engine and the
     SAME unlock — never a second product. It reveals the "Prepared for" field
     and lets build() pass opts.report; the free 5-receipt cap and the footer
     mark are applied elsewhere and are untouched by it. */
  var modeEl = $('mode'), preparedField = $('preparedField');
  function syncMode() { if (preparedField) preparedField.hidden = !(modeEl && modeEl.value === 'report'); }
  if (modeEl) { modeEl.addEventListener('change', syncMode); syncMode(); }

  // price + checkout slot. Empty config -> honest disabled button; a filled
  // CHECKOUT_URL -> a real buy link. The DELTA pattern, in this project.
  var priceEls = document.querySelectorAll('[data-price]');
  for (var pi = 0; pi < priceEls.length; pi++) priceEls[pi].textContent = String(priceUsd);
  renderBuy();

  if (unlockCode) {
    // The code row's visibility is set by renderBuy() just above: it is shown
    // exactly when a digest exists, so it can never go missing beside a live
    // buy link. Only the check handler is wired here.
    var wantDigest = String(unlockCode).trim().toLowerCase();
    $('codeBtn').addEventListener('click', function () {
      var msg = $('codeMsg'), btn = $('codeBtn'), v = $('codeInput').value.trim();
      if (!v) return;
      btn.disabled = true;
      msg.className = '';
      msg.textContent = 'Checking\u2026';
      digestHex(v).then(function (hex) {
        if (sameHex(hex, wantDigest)) {
          state.unlocked = true;
          try { localStorage.setItem(LS_KEY, '1'); } catch (e) {}
          msg.className = 'good';
          msg.textContent = 'Unlocked. Add as many receipts as you like.';
          renderList();
          renderBuy();
        } else {
          msg.className = 'bad';
          msg.textContent = 'That code was not recognised.';
        }
      }, function () {
        msg.className = 'bad';
        msg.textContent = 'This browser cannot check a code. Open the page over https and try again.';
      }).then(function () { btn.disabled = false; });
    });
  }

  updateControls();
  renderCap();
}

/* exposed for tests and for anyone who wants to poke at it */
window.RS = {
  buildPdf: buildPdf, parseDateFromName: parseDateFromName, normalizeImage: normalizeImage,
  clean: clean, state: state, addFiles: addFiles, loadSamples: loadSamples, build: build,
  sortByDate: sortByDate, csvFor: csvFor, reportGroups: reportGroups,
  get lastBlob() { return lastPdfBlob; },
  get lastCsvText() { return lastCsvText; }
};

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();

})();
