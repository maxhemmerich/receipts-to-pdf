#!/usr/bin/env python
# indexnow.py - tell IndexNow (Bing/Yandex and the engines that share the protocol) about this site's URLs.
#
# IndexNow needs no account: you host a key file whose NAME is the key and whose CONTENT is the key,
# then POST the URL list and point at that file with `keyLocation`. This site lives on a subpath of
# maxhemmerich.github.io, so the key file has to sit inside this project's own subpath - nothing can be
# placed at the host root - which is exactly what keyLocation is for.
#
# This is a BUILD-TIME POST, not an on-page request, so it does not touch the page's CSP
# (`connect-src 'none'` stays as it is); the browser never makes this call.
#
#   py -3.10 tools/indexnow.py            # print the payload, then POST it and print the real response
#   py -3.10 tools/indexnow.py --dry-run  # print the payload only, no request
#
# The URL list comes straight out of sitemap.xml, the build's own output, so this script cannot fall out
# of step with the site: add a page, rebuild the sitemap, and it is submitted here too.
import json, os, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINT = "https://api.indexnow.org/indexnow"
HOST = "maxhemmerich.github.io"
SITE = "https://%s/receipts-to-pdf" % HOST

key_path = os.path.join(ROOT, "indexnow.key")
if not os.path.exists(key_path):
    sys.exit("indexnow.key is missing - refusing to run. The key must not be regenerated silently: "
             "a new key means a new key file at a new URL, which invalidates what engines already saw.")
KEY = open(key_path, encoding="utf-8").read().strip()
if not KEY or len(KEY) < 8:
    sys.exit("indexnow.key does not hold a usable key (%r)" % KEY)

# The hosted key file, inside this project's own subpath. Written from indexnow.key so the two cannot drift.
key_file = os.path.join(ROOT, "%s.txt" % KEY)
open(key_file, "w", newline="\n", encoding="utf-8").write(KEY + "\n")

# URL list: straight out of the built sitemap.
sm = open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read()
URLS = [u.split("<", 1)[0] for u in sm.split("<loc>")[1:]]
if not URLS:
    sys.exit("no URLs found in sitemap.xml")

payload = {
    "host": HOST,
    "key": KEY,
    "keyLocation": "%s/%s.txt" % (SITE, KEY),
    "urlList": URLS,
}
body = json.dumps(payload).encode("utf-8")
print("key file   : %s/%s.txt  (local: %s)" % (SITE, KEY, os.path.relpath(key_file, ROOT).replace("\\", "/")))
print("endpoint   : %s" % ENDPOINT)
print("urls (%d)  : %s" % (len(URLS), ", ".join(URLS)))
print("payload    : %s" % body.decode("utf-8"))

if "--dry-run" in sys.argv:
    sys.exit(0)

req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                            headers={"Content-Type": "application/json; charset=utf-8"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        code, text = r.status, r.read().decode("utf-8", "replace")
        print("HTTP       : %s %s" % (code, r.reason))
        print("headers    : %s" % dict(r.getheaders()))
except urllib.error.HTTPError as e:
    code, text = e.code, e.read().decode("utf-8", "replace")
    print("HTTP       : %s %s" % (code, e.reason))
    print("headers    : %s" % dict(e.getheaders()))
except Exception as e:
    print("REQUEST FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(2)
print("body       : %r" % text)
