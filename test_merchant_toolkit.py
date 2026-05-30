"""End-to-end smoke test for the FastAPI Merchant Toolkit."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

# use an in-memory DB for testing
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"

from fastapi.testclient import TestClient

from app import app
import merchant_toolkit

# explicitly create tables (TestClient does not always trigger startup events)
merchant_toolkit.init_db()

with TestClient(app) as c:
    # 1) register
    r = c.post(
        "/merchant/register",
        data={"name": "Sharma Kirana", "vpa": "sharma@okicici", "phone": "9999999999"},
    )
    assert r.status_code == 204, r.status_code

    # 2) bootstrap PWA -- get secret + next_seq
    me = c.get("/merchant/api/me").json()
    print("me:", {k: me[k] for k in ("id", "vpa", "next_seq")})

    # 3) pre-issue printable batch
    batch = c.post("/merchant/api/batch", json={"count": 3}).json()
    print("batch tokens:", [t["token"] for t in batch["tokens"]])

    # 4) simulate OFFLINE mint of an amount-bound token (what the PWA does in JS)
    seq = me["next_seq"] + 10
    nonce = secrets.token_hex(8)
    amount_paise = 4250
    payload = f"{me['id']}|{seq}|{amount_paise}|{nonce}".encode()
    tok = base64.urlsafe_b64encode(
        hmac.new(bytes.fromhex(me["secret"]), payload, hashlib.sha256).digest()
    ).decode().rstrip("=")[:22]

    # 5) PWA later flushes claim queue
    r = c.post(
        "/merchant/api/reconcile/claim",
        json={"claims": [{
            "token": tok, "seq": seq, "nonce": nonce,
            "amount_paise": amount_paise, "ts": int(time.time() * 1000),
        }]},
    )
    print("claim accepted:", r.json())

    # 6) bank/PSP webhook fires
    r = c.post(
        "/merchant/api/webhook/upi",
        json={
            "vpa": "sharma@okicici", "token": tok, "utr": "UTR123456",
            "amount_paise": 4250, "payer_vpa": "alice@upi",
            "ts_ms": int(time.time() * 1000),
        },
    )
    print("webhook:", r.json())

    # 7) ledger should show one PAID row
    led = c.get("/merchant/api/ledger").json()
    print("totals:", led["totals"])
    print("rows:", json.dumps(led["rows"], indent=2))
    assert any(row["status"] == "paid" and row["token"] == tok for row in led["rows"])

    # 8) duplicate webhook is idempotent
    r = c.post(
        "/merchant/api/webhook/upi",
        json={
            "vpa": "sharma@okicici", "token": tok, "utr": "UTR123456",
            "amount_paise": 4250, "ts_ms": int(time.time() * 1000),
        },
    )
    assert r.json().get("status") == "duplicate", r.json()

    # 9) negative: bank reports unknown token -> unmatched
    c.post(
        "/merchant/api/webhook/upi",
        json={
            "vpa": "sharma@okicici", "token": "ZZ_unknown_token_____",
            "utr": "UTR999", "amount_paise": 100, "ts_ms": int(time.time() * 1000),
        },
    )
    led = c.get("/merchant/api/ledger").json()
    assert any(r["status"] == "unmatched" for r in led["rows"])

    # 10) /health
    assert c.get("/health").json() == {"status": "ok"}

    # 11) / redirects to /merchant/
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/merchant/"

print("\nOK: FastAPI offline -> claim -> settle -> reconcile works.")

