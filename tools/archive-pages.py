"""archive-pages.py — give every public page a third-party copy on the Wayback Machine.

WHY THIS EXISTS
    The site is a subpath of a shared host (maxhemmerich.github.io/receipts-to-pdf/).
    Google is waiting on Max's Search Console token and there is no host-root robots.txt,
    so the only discovery lever the crew still holds is a reference that lives OUTSIDE
    this project's own domain. An archive.org snapshot is exactly that: a permanent,
    third-party-hosted, linkable copy of a public page, with a date. This is the lane's
    first such reference.

WHAT IT DOES
    1. Reads every URL straight out of sitemap.xml, so the archive list cannot drift from
       the site.
    2. For each URL not already captured, asks the Wayback Machine to Save Page Now.
    3. Confirms the capture against the authoritative CDX index (the /wayback/available
       API is known to lag and is reported, but not trusted) and records timestamp + the
       snapshot URL in discovery/wayback-references.json.
    4. --verify re-checks the CDX index for every URL and asserts a HTTP 200 capture
       exists, without saving anything new.

    It writes to discovery/wayback-references.json only. It never touches the site, never
    adds anything to a page, and makes no claim about the tool. Archive.org is flaky and
    rate-limits anonymous saves, so every network step retries politely and the JSON is
    written after EVERY URL, so a later timeout never loses earlier progress.

USAGE
    py -3.10 tools/archive-pages.py            # save any page that has no 200 capture yet
    py -3.10 tools/archive-pages.py --refresh  # re-save EVERY url (a page changed after its capture)
    py -3.10 tools/archive-pages.py --verify   # only re-check the CDX index (no saves)
    py -3.10 tools/archive-pages.py --page X   # just one URL (by its sitemap path)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITEMAP = os.path.join(ROOT, "sitemap.xml")
OUT = os.path.join(ROOT, "discovery", "wayback-references.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
SLEEP_BETWEEN_SAVES = 20      # anonymous Save Page Now rate-limits hard
OFFLINE_MARKERS = ("Temporarily Offline", "temporarily offline",
                   "Internet Archive: Temporarily Offline")
LIMIT_MARKER = "reached the limit of active Save Page Now sessions"


# --------------------------------------------------------------------------- #
# small http helpers
# --------------------------------------------------------------------------- #
def http_get(url, timeout=60):
    """Return (status, body_bytes). Raises nothing for HTTP errors; returns the code."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""
    except Exception as e:  # noqa
        return None, str(e).encode("utf-8", "replace")


def sitemap_urls():
    html = open(SITEMAP, encoding="utf-8").read()
    return re.findall(r"<loc>\s*([^<]+?)\s*</loc>", html)


def is_offline(body):
    text = body.decode("utf-8", "replace")
    return any(m in text for m in OFFLINE_MARKERS)


# --------------------------------------------------------------------------- #
# archive.org
# --------------------------------------------------------------------------- #
def cdx_latest(url):
    """Newest HTTP-200 capture for `url` from the CDX index.

    Returns (timestamp, statuscode) for the newest row, or None if there is none.
    CDX is the authoritative index; the /wayback/available API lags behind it.
    """
    api = ("http://web.archive.org/cdx/search/cdx?url=%s&output=json"
           "&fl=timestamp,statuscode&filter=statuscode:200" % url)
    for attempt in range(3):
        code, body = http_get(api, timeout=45)
        if body and is_offline(body):
            print("    cdx: archive.org reports offline; retry %d" % (attempt + 1))
            time.sleep(8)
            continue
        text = (body or b"").decode("utf-8", "replace").strip()
        if not text or text.startswith("<"):
            time.sleep(6)
            continue
        try:
            rows = json.loads(text)
        except ValueError:
            time.sleep(6)
            continue
        rows = [r for r in rows[1:] if len(r) >= 2]  # drop the header row
        if rows:
            ts, sc = rows[-1]
            return ts, sc
        return None
    return None


def availability(url):
    """The /wayback/available answer, as a dict. Reported, not trusted (it lags)."""
    api = "https://archive.org/wayback/available?url=%s" % url
    code, body = http_get(api, timeout=30)
    try:
        return json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return {"error": "no json", "http": code}


def snapshot_url(url, ts):
    return "https://web.archive.org/web/%s/%s" % (ts, url)


def spn_save(url):
    """Ask the Wayback Machine to Save Page Now. Returns a short status string."""
    code, body = http_get("https://web.archive.org/save/%s" % url, timeout=150)
    text = (body or b"").decode("utf-8", "replace")
    if is_offline(body):
        return "offline"
    if LIMIT_MARKER in text:
        return "rate-limited"
    if code is None:
        return "error"
    return "http %s" % code


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #
def load_db():
    if os.path.exists(OUT):
        try:
            return json.loads(open(OUT, encoding="utf-8").read())
        except ValueError:
            pass
    return {"_note": ("Wayback Machine captures of this site's public pages. Written by "
                      "tools/archive-pages.py; verified against the CDX index, not the "
                      "lagging /wayback/available API."),
            "references": {}}


def save_db(db):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, sort_keys=True)
        f.write("\n")


def _record(key, refs, ts, sc, target, note=None):
    entry = {"snapshot": snapshot_url(target, ts), "timestamp": ts, "statuscode": sc}
    if note:
        entry["note"] = note
    refs[key] = entry
    print("  [done] %s  -> %s (%s)%s" % (key, ts, sc, ("  " + note) if note else ""))


def archive_one(url, refs, save=True, refresh=False):
    """Ensure `url` has a 200 capture; return a status string.

    With refresh=True a capture is re-saved even when one already exists, so a
    page whose content changed after its capture is re-archived instead of the
    record silently keeping the older revision.
    """
    have = None if refresh else cdx_latest(url)
    if have:
        ts, sc = have
        _record(url, refs, ts, sc, url)
        return "have"

    if not save:
        # the plain URL may be wedged; accept the recorded variant, same as a save would
        v = cdx_latest(url + "?v=1")
        if v:
            ts, sc = v
            _record(url, refs, ts, sc, url + "?v=1", "captured under '?v=1' (same static bytes)")
            return "have"
        print("  [none] %s  (no 200 capture)" % url)
        return "none"

    # Archive.org can wedge a single URL's Save-Page-Now entry so it keeps replaying a stale
    # "not archived" page and never fetches the origin. A '?v=1' variant is the same static
    # bytes under a different key, so it is a faithful fallback -- and it is recorded with a
    # note, so the record never pretends the snapshot was taken at the bare URL.
    variants = ((url, None), (url + "?v=1", "captured under '?v=1' (same static bytes)"))
    for target, note in variants:
        for _ in range(2):
            st = spn_save(target)
            print("  [save] %s  -> %s" % (target, st))
            if st in ("offline", "rate-limited", "error"):
                time.sleep(45 if st == "rate-limited" else 30)
                continue
            for _ in range(6):
                time.sleep(10)
                have = cdx_latest(target)
                if have:
                    ts, sc = have
                    _record(url, refs, ts, sc, target, note)
                    return "saved"
            break
    print("  [FAIL] %s  (no 200 capture yet)" % url)
    return "fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="only re-check the CDX index; save nothing")
    ap.add_argument("--refresh", action="store_true",
                    help="re-save every URL even if a capture exists, so a page whose "
                         "content changed after its capture is re-archived")
    ap.add_argument("--page", default=None, help="limit to one sitemap URL (exact match)")
    a = ap.parse_args()

    urls = sitemap_urls()
    if a.page:
        urls = [u for u in urls if u == a.page or u.endswith("/" + a.page)]
        if not urls:
            sys.exit("no sitemap URL matches %r" % a.page)

    db = load_db()
    refs = db.setdefault("references", {})

    print("check: archive captures for %d public URL(s) (%s)"
          % (len(urls), "verify" if a.verify else ("refresh" if a.refresh else "save")))
    for i, url in enumerate(urls):
        archive_one(url, refs, save=not a.verify, refresh=a.refresh and not a.verify)
        save_db(db)  # write after every URL so a timeout never loses progress
        if not a.verify and i < len(urls) - 1:
            time.sleep(SLEEP_BETWEEN_SAVES)

    missing = [u for u in urls if u not in refs]
    print()
    if missing:
        print("INCOMPLETE — %d URL(s) still have no 200 capture:" % len(missing))
        for u in missing:
            print("  - " + u)
        sys.exit(1)
    print("OK — every URL has a 200 capture on the Wayback Machine.")
    for u in urls:
        r = refs[u]
        av = availability(u)
        snap = av.get("archived_snapshots", {}).get("closest", {})
        note = ("available:%s status:%s" % (snap.get("available"), snap.get("status"))
                if snap else "availability-api: (lagging)")
        print("  %-72s %s  [%s]" % (u, r["timestamp"], note))


if __name__ == "__main__":
    main()
