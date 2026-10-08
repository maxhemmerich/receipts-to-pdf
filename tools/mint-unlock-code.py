#!/usr/bin/env python3
"""Mint a ReceiptStack unlock code, and the digest config.js carries.

    py -3 tools/mint-unlock-code.py                 # mint a fresh code + digest
    py -3 tools/mint-unlock-code.py --check <code>  # digest of a code you already have

The page derives the same value in the browser with WebCrypto:

    PBKDF2-HMAC-SHA256(normalise(code), salt, 210000, 32 bytes)  ->  hex

salt = b"receiptstack.unlock.v1" (see UNLOCK_SALT in assets/app.js)
normalise = delete every space and hyphen, then upper-case

The CODE goes to the buyer. The DIGEST goes into config.js as UNLOCK_CODE.
Publishing the digest is safe only while the code is high entropy, which is why
the minted code is 25 random RFC-4648 base32 characters (125 bits). Keep the
code out of this repository: config.js is public and it must never hold it.
"""
import argparse
import hashlib
import secrets

SALT = b"receiptstack.unlock.v1"
ITER = 210000
DKLEN = 32
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def normalise(code):
    return "".join(code.split()).replace("-", "").upper()


def digest(code):
    return hashlib.pbkdf2_hmac("sha256", normalise(code).encode("utf-8"), SALT, ITER, DKLEN).hex()


def mint(n=25):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def group(s, n=5):
    return " ".join(s[i:i + n] for i in range(0, len(s), n))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", metavar="CODE", help="print the digest of CODE instead of minting")
    ap.add_argument("--length", type=int, default=26, help="characters to mint (default 26)")
    args = ap.parse_args()

    if args.check:
        code = args.check
        print("code    : %s" % group(normalise(code)))
        print("digest  : %s" % digest(code))
        return

    if args.length < 20:
        raise SystemExit("refusing: a code shorter than 20 characters is brute-forceable "
                         "offline because the digest is public")

    code = mint(args.length)
    d = digest(code)
    assert digest(group(code)) == d, "normalisation is not idempotent for the spaced form"
    assert digest(code.lower()) == d, "normalisation is not case-insensitive"

    print("code    : %s" % group(code))
    print("digest  : %s" % d)
    print()
    print("Give the code to the buyer. Paste this line into config.js:")
    print('const UNLOCK_CODE  = "%s";' % d)
    print()
    print("Spaces and hyphens in the code are ignored; case does not matter.")


if __name__ == "__main__":
    main()
