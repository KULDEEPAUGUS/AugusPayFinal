# Auguspay™ — Offline-tolerant Merchant Toolkit (FastAPI)

> **© 2026 Kuldeep Chotiya. All Rights Reserved.**
> Auguspay™ is a registered trade name of Kuldeep Chotiya. The source code,
> design, brand, and accompanying documentation are proprietary. Resale,
> sublicensing, or commercial deployment without prior written permission
> from the owner is **prohibited**. See [LICENSE](./LICENSE) for the full terms.

> A Progressive Web App that lets kirana merchants keep issuing dynamic, reconcilable UPI QR codes even when the shops internet is down -- relying on the customers connectivity for the actual UPI rails.
Offline-tolerant merchant tool, not "offline payments." Money still moves over UPI (always online) via the customers phone. What goes offline is the merchants device -- so the shop never has to turn a customer away when its WiFi dies.
## Problem
- Owners phone loses connectivity all the time (rural 4G, basements, festival-day congestion).
- Existing merchant apps need merchant-side internet to generate a dynamic-amount QR.
- Static printed QRs work, but the owner cannot tell which sale a given bank SMS corresponds to.
## Solution
- PWA that installs to the home screen and boots from cache.
- Each fresh QR is minted on the device via cached HMAC secret (browser WebCrypto).
- Every QR carries a 22-char signed token in the UPI `tr` field, so the banks settlement webhook can join back to the exact sale.
- Live confirmation via Server-Sent Events: when the bank webhook fires, the QR screen auto-flips to PAID and beeps.
- If the device is offline, claims queue in IndexedDB and flush automatically when connectivity returns.
## Token scheme
```
token = base64url( HMAC_SHA256( merchant_secret,
                                "<merchant_id>|<seq>|<amount_paise>|<nonce>" ) )[:22]
```
## Verification statuses
- Paid       -- claim + settlement both present, amounts match
- Pending    -- claim present, settlement not yet received
- Disputed   -- both present, amounts disagree
- Unmatched  -- settlement present but no claim (direct transfer / fraud)
## Run it locally
```
pip install -r requirements.txt
copy .env.example .env
python app.py
# or:  uvicorn app:app --reload --port 5000
# open http://127.0.0.1:5000/  -> redirects to /merchant/
```
OpenAPI / Swagger UI at http://127.0.0.1:5000/docs
In DevTools toggle Network -> Offline and you can still mint QRs and queue sales. Toggle back online -> queue drains and the ledger fills.
## Simulate a bank settlement
```powershell
$body = @{
  vpa = "yourname@okicici"
  token = "<token from QR>"
  utr = "UTR" + (Get-Random)
  amount_paise = 5000
  payer_vpa = "alice@upi"
  ts_ms = [int64]((Get-Date) - (Get-Date "1970-01-01")).TotalMilliseconds
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:5000/merchant/api/webhook/upi `
                  -Method POST -ContentType "application/json" -Body $body
```
## End-to-end test
```
python test_merchant_toolkit.py
```
## API
| Method | Path | Purpose |
|---|---|---|
| GET  | `/`                                     | redirects to /merchant/ |
| GET  | `/health`                               | liveness probe |
| GET  | `/docs`                                 | OpenAPI / Swagger UI |
| GET  | `/merchant/`                            | register page or dashboard |
| POST | `/merchant/register`                    | create shop |
| POST | `/merchant/logout`                      | clear session |
| GET  | `/merchant/api/me`                      | bootstrap PWA |
| POST | `/merchant/api/batch`                   | pre-issue N tokens |
| GET  | `/merchant/api/qr.png?upi=...`          | render QR PNG |
| POST | `/merchant/api/reconcile/claim`         | flush queued offline claims |
| GET  | `/merchant/api/ledger`                  | totals + reconciled rows |
| GET  | `/merchant/api/events`                  | SSE stream of live settlements |
| POST | `/merchant/api/webhook/upi`             | bank/PSP settlement callback |
### Webhook signature
Set `MERCHANT_WEBHOOK_SECRET`. PSP must send `X-Auguspay-Signature: <hex hmac-sha256 of body>`.
## Stack
- FastAPI + Uvicorn (async, OpenAPI, type-checked endpoints)
- SQLAlchemy 2.0 (sync) + SQLite (swap DATABASE_URL for Postgres)
- Pydantic v2 for request/response validation
- Starlette SessionMiddleware for merchant cookie auth
- Jinja2 templates
- PWA: Service Worker + Web App Manifest + IndexedDB
- WebCrypto HMAC-SHA256 for client-side token minting
- Server-Sent Events for live PAID push
## What this is honestly NOT
- Not a replacement for GPay/PhonePe.
- Not "offline payments" -- UPI requires the customers device to be online.
- Not integrated with a real PSP yet (webhook shape + signature check are ready).
- Not multi-worker scalable as-is (SSE is in-process; swap for Redis pub/sub).
## Files
```
app.py                       FastAPI entrypoint + middleware + static mount
merchant_toolkit.py          Router, models, HMAC, API, SSE pub/sub
test_merchant_toolkit.py     End-to-end smoke test (FastAPI TestClient)
templates/merchant/          register.html, dashboard.html
static/merchant/             app.js, sw.js, manifest, style.css
requirements.txt, .env.example
```
## Roadmap
1. Razorpay / Cashfree adapter for /api/webhook/upi.
2. Client-side QR rendering so the QR image draws even when offline.
3. Redis pub/sub for multi-worker SSE.
4. Pytest + GitHub Actions CI.
5. Dockerfile + Cloud Run deployment.
6. UPI Lite acceptance via NPCI-certified PSP (true end-to-end offline).

---

## License & Ownership

**Auguspay™ © 2026 Kuldeep Chotiya. All Rights Reserved.**

This is **proprietary software**, not open-source. By cloning, viewing, or
running this project you accept the terms of [LICENSE](./LICENSE). In summary:

- ✅ Personal evaluation, learning, and portfolio review are allowed.
- ❌ You may **not** sell, sublicense, rent, white-label, or deploy this
  software as a paid or free service for third parties.
- ❌ You may **not** use the brand name "Auguspay" or any confusingly
  similar mark in your own product.
- ❌ You may **not** remove or alter the copyright and attribution notices.
- ✉️ Commercial licensing is available — contact **Kuldeep Chotiya**.

> Author / Owner: **Kuldeep Chotiya**, 2026.

