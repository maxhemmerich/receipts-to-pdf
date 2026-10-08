/* ReceiptStack — site config. Loaded before assets/app.js, exactly like DELTA.
   Two things to paste in when the checkout exists:
     CHECKOUT_URL — the checkout link. While it is "" the buy button is a
                    disabled, honest "Checkout isn't connected yet".
     UNLOCK_CODE  — the DIGEST of the code a buyer is given, never the code
                    itself. Mint one with tools/mint-unlock-code.py, which
                    prints the code (that goes to the buyer) and the digest
                    (that goes here, as a 64-character hex string). While it is
                    "" the code box stays hidden, because no code could work.
                    Never paste the plain code: this file is public, and a
                    published code unlocks the page for everyone. The code
                    must be high entropy (>= 20 random characters) because the
                    digest is public and a weak code can be brute-forced.
   PRICE_USD is the price shown on the page and on the buy button. */
const CHECKOUT_URL = "";
const UNLOCK_CODE  = "";
const PRICE_USD    = 9;
