"""
Auguspay -- Offline-tolerant Merchant Toolkit (FastAPI version)
===============================================================

Issue, rotate, and reconcile UPI QRs for kirana stores. The merchant's
device can be offline; QRs are minted in-browser via WebCrypto using a
cached HMAC secret. Bank/PSP webhooks confirm settlements; the dashboard
auto-updates over Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import os
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import segno
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///auguspay.db")

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    # in-memory DB must share one connection across the app
    if ":memory:" in DATABASE_URL:
        _engine_kwargs["poolclass"] = StaticPool

_engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    vpa = Column(String(256), nullable=False)
    phone = Column(String(20), nullable=False, unique=True)
    secret = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class QrToken(Base):
    __tablename__ = "qr_tokens"
    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    token = Column(String(64), nullable=False, unique=True, index=True)
    amount_paise = Column(Integer, nullable=True)
    nonce = Column(String(32), nullable=False)
    minted_at = Column(DateTime, default=_utcnow)
    source = Column(String(16), default="online")
    __table_args__ = (UniqueConstraint("merchant_id", "seq", name="uq_merchant_seq"),)


class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    token = Column(String(64), nullable=False, index=True)
    amount_paise = Column(Integer, nullable=False)
    claimed_at = Column(DateTime, nullable=False)
    synced_at = Column(DateTime, default=_utcnow)


class Settlement(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    token = Column(String(64), nullable=True, index=True)
    utr = Column(String(64), nullable=False, unique=True)
    amount_paise = Column(Integer, nullable=False)
    payer_vpa = Column(String(256), nullable=True)
    settled_at = Column(DateTime, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(_engine)


# ---------------------------------------------------------------------------
# HMAC token scheme (must match static/merchant/app.js:mintToken)
# ---------------------------------------------------------------------------


def mint_token(secret_hex: str, merchant_id: int, seq: int,
               amount_paise: Optional[int], nonce: str) -> str:
    amt = "" if amount_paise is None else str(amount_paise)
    payload = f"{merchant_id}|{seq}|{amt}|{nonce}".encode()
    key = bytes.fromhex(secret_hex)
    digest = hmac.new(key, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:22]


def verify_token(secret_hex: str, merchant_id: int, seq: int,
                 amount_paise: Optional[int], nonce: str, token: str) -> bool:
    return hmac.compare_digest(
        token, mint_token(secret_hex, merchant_id, seq, amount_paise, nonce)
    )


def _upi_url(vpa: str, name: str, amount_paise: Optional[int], token: str) -> str:
    parts = [f"pa={vpa}", f"pn={name}", f"tr={token}"]
    if amount_paise:
        parts.append(f"am={amount_paise / 100:.2f}")
    return "upi://pay?" + "&".join(parts)


# ---------------------------------------------------------------------------
# In-process pub/sub for live settlement events (SSE)
# ---------------------------------------------------------------------------

_subs: dict[int, list[asyncio.Queue]] = defaultdict(list)
_subs_lock = asyncio.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None


def _capture_loop() -> None:
    """Called once at startup so background threads (rare here) can publish."""
    global _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = None


async def _subscribe(merchant_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=32)
    async with _subs_lock:
        _subs[merchant_id].append(q)
    return q


async def _unsubscribe(merchant_id: int, q: asyncio.Queue) -> None:
    async with _subs_lock:
        if q in _subs[merchant_id]:
            _subs[merchant_id].remove(q)


async def _publish(merchant_id: int, event: dict) -> None:
    # snapshot subscribers under the lock, deliver outside
    async with _subs_lock:
        targets = list(_subs[merchant_id])
    for q in targets:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# Router + helpers
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/merchant", tags=["merchant"])
templates = Jinja2Templates(directory="templates")


def _current_merchant(request: Request, db: Session) -> Optional[Merchant]:
    mid = request.session.get("merchant_id")
    if not mid:
        return None
    return db.get(Merchant, mid)


def _require_merchant(request: Request, db: Session = Depends(get_db)) -> Merchant:
    m = _current_merchant(request, db)
    if not m:
        raise HTTPException(status_code=401, detail="not registered")
    return m


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    m = _current_merchant(request, db)
    if m:
        return templates.TemplateResponse(
            request, "merchant/dashboard.html", {"merchant": m}
        )
    return templates.TemplateResponse(request, "merchant/register.html")


@router.post("/register", status_code=status.HTTP_204_NO_CONTENT)
def register(
    request: Request,
    name: str = Form(...),
    vpa: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    name, vpa, phone = name.strip(), vpa.strip(), phone.strip()
    if "@" not in vpa or not name or not phone:
        raise HTTPException(status_code=400, detail="invalid input")
    existing = db.scalar(select(Merchant).where(Merchant.phone == phone))
    if existing:
        request.session["merchant_id"] = existing.id
        return Response(status_code=204)
    m = Merchant(name=name, vpa=vpa, phone=phone, secret=secrets.token_hex(32))
    db.add(m)
    db.commit()
    db.refresh(m)
    request.session["merchant_id"] = m.id
    return Response(status_code=204)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request):
    request.session.pop("merchant_id", None)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


@router.get("/api/me")
def api_me(m: Merchant = Depends(_require_merchant), db: Session = Depends(get_db)):
    max_seq = db.scalar(
        select(func.coalesce(func.max(QrToken.seq), 0)).where(
            QrToken.merchant_id == m.id
        )
    ) or 0
    return {
        "id": m.id, "name": m.name, "vpa": m.vpa, "phone": m.phone,
        "secret": m.secret, "next_seq": max_seq + 1,
    }


class BatchReq(BaseModel):
    count: int = Field(20, ge=1, le=200)


@router.post("/api/batch")
def api_batch(
    body: BatchReq,
    m: Merchant = Depends(_require_merchant),
    db: Session = Depends(get_db),
):
    start = (db.scalar(
        select(func.coalesce(func.max(QrToken.seq), 0)).where(
            QrToken.merchant_id == m.id
        )
    ) or 0) + 1
    out = []
    for i in range(body.count):
        seq = start + i
        nonce = secrets.token_hex(8)
        tok = mint_token(m.secret, m.id, seq, None, nonce)
        db.add(QrToken(
            merchant_id=m.id, seq=seq, token=tok, amount_paise=None,
            nonce=nonce, source="online",
        ))
        out.append({
            "seq": seq, "token": tok, "nonce": nonce,
            "upi": _upi_url(m.vpa, m.name, None, tok),
        })
    db.commit()
    return {"tokens": out}


@router.get("/api/qr.png")
def api_qr_png(upi: str = Query(..., min_length=6)):
    if not upi.startswith("upi://"):
        raise HTTPException(status_code=400, detail="bad upi url")
    buf = io.BytesIO()
    segno.make(upi, error="h").save(buf, kind="png", scale=8, border=2)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


class ClaimIn(BaseModel):
    token: str
    amount_paise: int
    ts: int  # epoch ms
    seq: Optional[int] = None
    nonce: Optional[str] = None


class ClaimsReq(BaseModel):
    claims: list[ClaimIn]


@router.post("/api/reconcile/claim")
async def api_claim(
    body: ClaimsReq,
    m: Merchant = Depends(_require_merchant),
    db: Session = Depends(get_db),
):
    accepted = 0
    for c in body.claims:
        slot = db.scalar(
            select(QrToken).where(
                QrToken.merchant_id == m.id, QrToken.token == c.token
            )
        )
        if not slot and c.seq is not None and c.nonce is not None:
            if verify_token(m.secret, m.id, c.seq, c.amount_paise, c.nonce, c.token):
                slot = QrToken(
                    merchant_id=m.id, seq=c.seq, token=c.token,
                    amount_paise=c.amount_paise, nonce=c.nonce, source="offline",
                )
                db.add(slot)
        if not slot:
            continue
        db.add(Claim(
            merchant_id=m.id, token=c.token, amount_paise=c.amount_paise,
            claimed_at=datetime.fromtimestamp(c.ts / 1000, tz=timezone.utc),
        ))
        accepted += 1
    db.commit()
    if accepted:
        await _publish(m.id, {"type": "claim", "accepted": accepted})
    return {"accepted": accepted}


@router.get("/api/ledger")
def api_ledger(
    m: Merchant = Depends(_require_merchant), db: Session = Depends(get_db)
):
    claims = db.scalars(select(Claim).where(Claim.merchant_id == m.id)).all()
    settlements = db.scalars(
        select(Settlement).where(Settlement.merchant_id == m.id)
    ).all()
    s_by_token = {s.token: s for s in settlements if s.token}
    c_by_token: dict[str, Claim] = {}
    for c in claims:
        if c.token not in c_by_token or c.claimed_at > c_by_token[c.token].claimed_at:
            c_by_token[c.token] = c

    rows = []
    for token, claim in c_by_token.items():
        sett = s_by_token.get(token)
        if sett:
            status_ = "paid" if sett.amount_paise == claim.amount_paise else "disputed"
        else:
            status_ = "pending"
        rows.append({
            "token": token,
            "amount": claim.amount_paise / 100,
            "claimed_at": claim.claimed_at.isoformat(),
            "settled_at": sett.settled_at.isoformat() if sett else None,
            "utr": sett.utr if sett else None,
            "status": status_,
        })
    for token, s in s_by_token.items():
        if token in c_by_token:
            continue
        rows.append({
            "token": token, "amount": s.amount_paise / 100,
            "claimed_at": None, "settled_at": s.settled_at.isoformat(),
            "utr": s.utr, "status": "unmatched",
        })
    rows.sort(key=lambda r: r["settled_at"] or r["claimed_at"], reverse=True)
    totals = {
        k: round(sum(r["amount"] for r in rows if r["status"] == k), 2)
        for k in ("paid", "pending", "unmatched", "disputed")
    }
    return {"rows": rows, "totals": totals}


# ---------------------------------------------------------------------------
# Webhook + SSE
# ---------------------------------------------------------------------------


class WebhookIn(BaseModel):
    vpa: str
    utr: str
    amount_paise: int
    ts_ms: int
    token: Optional[str] = None
    payer_vpa: Optional[str] = None


@router.post("/api/webhook/upi")
async def api_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    expected_secret = os.environ.get("MERCHANT_WEBHOOK_SECRET")
    if expected_secret:
        sig = request.headers.get("x-auguspay-signature", "")
        good = hmac.new(expected_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            raise HTTPException(status_code=401, detail="bad signature")
    try:
        data = WebhookIn.model_validate_json(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad body: {e}")

    m = db.scalar(select(Merchant).where(Merchant.vpa == data.vpa))
    if not m:
        raise HTTPException(status_code=404, detail="unknown merchant vpa")
    if db.scalar(select(Settlement).where(Settlement.utr == data.utr)):
        return {"status": "duplicate"}

    settled_at = datetime.fromtimestamp(data.ts_ms / 1000, tz=timezone.utc)
    db.add(Settlement(
        merchant_id=m.id, token=data.token, utr=data.utr,
        amount_paise=data.amount_paise, payer_vpa=data.payer_vpa,
        settled_at=settled_at,
    ))
    db.commit()
    await _publish(m.id, {
        "type": "settlement",
        "token": data.token, "utr": data.utr,
        "amount_paise": data.amount_paise, "payer_vpa": data.payer_vpa,
        "settled_at": settled_at.isoformat(),
    })
    return {"status": "ok"}


@router.get("/api/events")
async def api_events(request: Request, db: Session = Depends(get_db)):
    # Do NOT use _require_merchant here: returning 401 makes EventSource
    # auto-reconnect every few seconds *forever*. The spec says only 204
    # tells the browser to stop. So when there's no session, send 204
    # and the loop dies cleanly.
    m = _current_merchant(request, db)
    if m is None:
        return Response(status_code=204)
    mid = m.id

    async def stream():
        q = await _subscribe(mid)
        try:
            yield f"event: hello\ndata: {json.dumps({'merchant_id': mid})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"event: {evt['type']}\ndata: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            await _unsubscribe(mid, q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# PWA assets (served via the main app's StaticFiles mount; these wrappers
# keep tidy URLs at the same origin/scope as the dashboard)
# ---------------------------------------------------------------------------


@router.get("/manifest.webmanifest")
def manifest():
    path = os.path.join("static", "merchant", "manifest.webmanifest")
    with open(path, "rb") as f:
        return Response(content=f.read(), media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker():
    path = os.path.join("static", "merchant", "sw.js")
    with open(path, "rb") as f:
        return Response(
            content=f.read(),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/merchant/"},
        )

