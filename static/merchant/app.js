/* Auguspay POS — offline-first logic.
 *
 * Flow:
 *  - On first online load, fetch /merchant/api/me and cache {id, vpa, name, secret, nextSeq}
 *    in IndexedDB.  After that, the POS can boot completely offline.
 *  - "Collect" mints a fresh QR LOCALLY using WebCrypto HMAC-SHA256 with the
 *    cached secret. No network needed.
 *  - "Customer paid" enqueues a claim {token, seq, nonce, amount_paise, ts}
 *    in IndexedDB.
 *  - Whenever the network comes back (or "Sync" is pressed), the queue is
 *    POSTed to /merchant/api/reconcile/claim and the ledger refreshes.
 */

// ---------- tiny IndexedDB wrapper ----------
const DB_NAME = 'auguspay';
const DB_VER = 1;
function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB_NAME, DB_VER);
    r.onupgradeneeded = () => {
      const db = r.result;
      db.createObjectStore('kv');
      db.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
    };
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function kvGet(k) {
  const db = await idb();
  return new Promise((res) => {
    const tx = db.transaction('kv', 'readonly').objectStore('kv').get(k);
    tx.onsuccess = () => res(tx.result);
  });
}
async function kvSet(k, v) {
  const db = await idb();
  return new Promise((res) => {
    const tx = db.transaction('kv', 'readwrite').objectStore('kv').put(v, k);
    tx.onsuccess = () => res();
  });
}
async function qPush(item) {
  const db = await idb();
  return new Promise((res) => {
    const tx = db.transaction('queue', 'readwrite').objectStore('queue').add(item);
    tx.onsuccess = () => res();
  });
}
async function qAll() {
  const db = await idb();
  return new Promise((res) => {
    const tx = db.transaction('queue', 'readonly').objectStore('queue').getAll();
    tx.onsuccess = () => res(tx.result);
  });
}
async function qClear(ids) {
  const db = await idb();
  const store = db.transaction('queue', 'readwrite').objectStore('queue');
  for (const id of ids) store.delete(id);
  return new Promise((res) => { store.transaction.oncomplete = res; });
}

// ---------- HMAC token (must match merchant_toolkit.py:mint_token) ----------
function hexToBytes(hex) {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(hex.substr(i * 2, 2), 16);
  return b;
}
function b64urlNoPad(bytes) {
  let s = btoa(String.fromCharCode.apply(null, bytes));
  return s.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
async function mintToken(secretHex, merchantId, seq, amountPaise, nonceHex) {
  const amt = amountPaise == null ? '' : String(amountPaise);
  const payload = new TextEncoder().encode(`${merchantId}|${seq}|${amt}|${nonceHex}`);
  const key = await crypto.subtle.importKey(
    'raw', hexToBytes(secretHex),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', key, payload));
  return b64urlNoPad(sig).slice(0, 22);
}
function randomNonceHex() {
  const b = new Uint8Array(8);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

// ---------- bootstrap ----------
let me = null;
async function loadMe() {
  me = await kvGet('me');
  if (navigator.onLine) {
    // Always validate the cached identity against the server. If the server
    // session is gone (DB reset, cookie expired, different browser, etc.)
    // we must NOT keep using stale credentials -- that causes the dreaded
    // 401-reconnect loop on /api/events.
    try {
      const r = await fetch('/merchant/api/me');
      if (r.ok) {
        me = await r.json();
        await kvSet('me', me);
      } else if (r.status === 401) {
        await kvSet('me', null);
        me = null;
      }
    } catch (_) { /* offline -- use cached me if any */ }
  }
}

// ---------- UI ----------
const $ = (id) => document.getElementById(id);
let current = null; // {seq, nonce, token, amount_paise, upi}
let waiting = null; // token currently displayed, awaiting auto-confirm

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.15, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    o.start(); o.stop(ctx.currentTime + 0.4);
  } catch (e) { /* no audio context, ignore */ }
}

function showConfirmed(amount_paise, utr) {
  $('qrTok').textContent = '✅ PAID';
  $('qrAmt').textContent = (amount_paise / 100).toFixed(2);
  $('qrImg').style.opacity = '0.25';
  beep();
  // auto-clear after 3s so the next sale can start
  setTimeout(() => {
    current = null; waiting = null;
    $('qrBox').hidden = true;
    $('qrImg').style.opacity = '1';
    $('amt').value = ''; $('amt').focus();
    refreshLedger();
  }, 3000);
}

async function nextSeq() {
  me.next_seq = (me.next_seq || 1) + 1;
  await kvSet('me', me);
  return me.next_seq - 1;
}

async function makeQr(amountRupees) {
  const amt = Math.round(amountRupees * 100);
  const seq = await nextSeq();
  const nonce = randomNonceHex();
  const token = await mintToken(me.secret, me.id, seq, amt, nonce);
  const upi = `upi://pay?pa=${encodeURIComponent(me.vpa)}` +
              `&pn=${encodeURIComponent(me.name)}` +
              `&am=${(amt / 100).toFixed(2)}&tr=${token}`;
  current = { seq, nonce, token, amount_paise: amt, upi };
  $('qrTok').textContent = token;
  $('qrAmt').textContent = (amt / 100).toFixed(2);
  // QR PNG: use online endpoint if available, else use local fallback URL
  // (the segno endpoint isn't reachable offline; instead show the upi:// link
  //  and let the merchant tap to open a paired phone app, OR fall back to a
  //  data: QR via an inline lib in the future. For MVP: try, then text.)
  $('qrImg').src = '/merchant/api/qr.png?upi=' + encodeURIComponent(upi);
  $('qrImg').onerror = () => {
    $('qrImg').replaceWith(Object.assign(document.createElement('pre'),
      { textContent: upi, className: 'fallback' }));
  };
  $('qrImg').style.opacity = '1';
  $('qrBox').hidden = false;
  waiting = token;  // SSE handler will auto-confirm if a settlement arrives
}

async function recordPaid() {
  if (!current) return;
  await qPush({
    token: current.token, seq: current.seq, nonce: current.nonce,
    amount_paise: current.amount_paise, ts: Date.now(),
  });
  current = null;
  $('qrBox').hidden = true;
  $('amt').value = '';
  $('amt').focus();
  await refreshQueueLabel();
  trySync();
}

async function refreshQueueLabel() {
  const q = await qAll();
  $('queueLabel').textContent = `${q.length} queued`;
}

async function trySync() {
  if (!navigator.onLine) return;
  const q = await qAll();
  if (!q.length) { await refreshLedger(); return; }
  const r = await fetch('/merchant/api/reconcile/claim', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claims: q }),
  });
  if (r.ok) {
    await qClear(q.map((x) => x.id));
    await refreshQueueLabel();
    await refreshLedger();
  }
}

async function refreshLedger() {
  if (!navigator.onLine) return;
  const r = await fetch('/merchant/api/ledger');
  if (!r.ok) return;
  const data = await r.json();
  $('tPaid').textContent = '₹' + data.totals.paid.toFixed(2);
  $('tPending').textContent = '₹' + data.totals.pending.toFixed(2);
  $('tUnmatched').textContent = '₹' + data.totals.unmatched.toFixed(2);
  $('tDisputed').textContent = '₹' + data.totals.disputed.toFixed(2);
  $('ledgerBody').innerHTML = data.rows.map((r) => `
    <tr class="s-${r.status}">
      <td>${(r.settled_at || r.claimed_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td><code>${r.token}</code></td>
      <td>₹${r.amount.toFixed(2)}</td>
      <td>${r.status}</td>
      <td>${r.utr || ''}</td>
    </tr>`).join('');
}

function setNet() {
  const on = navigator.onLine;
  $('net').className = 'dot ' + (on ? 'on' : 'off');
  $('netLabel').textContent = on ? 'online' : 'offline';
  if (on) { trySync(); openEvents(); }
}

// ---------- live confirmation via Server-Sent Events ----------
let es = null;
let esRetryTimer = null;
function openEvents() {
  if (es || !navigator.onLine || !me) return;
  try {
    es = new EventSource('/merchant/api/events');
    es.addEventListener('settlement', (e) => {
      const d = JSON.parse(e.data);
      if (waiting && d.token === waiting) {
        showConfirmed(d.amount_paise, d.utr);
      } else {
        refreshLedger();
        beep();
      }
    });
    es.addEventListener('claim', () => refreshLedger());
    es.onerror = async () => {
      try { es && es.close(); } catch (_) {}
      es = null;
      // EventSource does not expose the HTTP status; probe /api/me to learn
      // whether this was a transient network blip or an auth failure.
      try {
        const r = await fetch('/merchant/api/me');
        if (r.status === 401) {
          await kvSet('me', null);
          me = null;
          if (esRetryTimer) { clearTimeout(esRetryTimer); esRetryTimer = null; }
          location.href = '/merchant/';
          return;
        }
      } catch (_) { /* offline -- fall through, retry later */ }
      // genuine transient error -- retry once, with backoff
      if (!esRetryTimer) {
        esRetryTimer = setTimeout(() => { esRetryTimer = null; openEvents(); }, 5000);
      }
    };
  } catch (e) { console.warn('SSE failed', e); }
}

async function genBatch() {
  if (!navigator.onLine) { alert('Need internet once to pre-issue a printable batch.'); return; }
  const n = parseInt($('batchN').value, 10) || 20;
  const r = await fetch('/merchant/api/batch', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count: n }),
  });
  const data = await r.json();
  // bump local nextSeq so offline minting doesn't collide
  me.next_seq = Math.max(me.next_seq || 1, ...data.tokens.map((t) => t.seq)) + 1;
  await kvSet('me', me);
  $('batchOut').innerHTML = data.tokens.map((t) => `
    <figure>
      <img src="/merchant/api/qr.png?upi=${encodeURIComponent(t.upi)}" alt="">
      <figcaption>#${t.seq} · ${t.token}</figcaption>
    </figure>`).join('');
}

// ---------- wire up ----------
window.addEventListener('online', setNet);
window.addEventListener('offline', setNet);

$('payForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const v = parseFloat($('amt').value);
  if (v > 0) makeQr(v);
});
$('paidBtn').addEventListener('click', recordPaid);
$('cancelBtn').addEventListener('click', () => {
  current = null; $('qrBox').hidden = true; $('amt').focus();
});
$('syncBtn').addEventListener('click', trySync);
$('batchBtn').addEventListener('click', genBatch);
$('logoutBtn').addEventListener('click', async () => {
  await fetch('/merchant/logout', { method: 'POST' });
  await kvSet('me', null);
  location.href = '/merchant/';
});

(async () => {
  await loadMe();
  if (!me) { location.href = '/merchant/'; return; }
  setNet();
  await refreshQueueLabel();
  await refreshLedger();
  // service worker is registered by install.js (loaded on every page)
})();

