/* Auguspay PWA install helper.
 *
 * Usage in any page:
 *   <button id="installBtn" hidden>Install app</button>
 *   <p id="iosHint" hidden>...</p>
 *   <script src="/static/merchant/install.js"></script>
 *
 * Behaviour:
 *  - On supported browsers (Chrome / Edge / Samsung / Android FF):
 *      captures `beforeinstallprompt`, reveals the button.
 *      On click, shows the native install dialog.
 *  - On iOS Safari (no beforeinstallprompt support):
 *      shows the #iosHint element with manual "Share -> Add to Home Screen"
 *      instructions, since that's the only path on iOS.
 *  - When the app is already installed (running in standalone display mode
 *      OR navigator.standalone on iOS), hides everything -- nothing to do.
 */

(function () {
  // --- register the service worker (idempotent across pages)
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker
      .register('/merchant/sw.js', { scope: '/merchant/' })
      .catch((e) => console.warn('SW register failed', e));
  }

  const btn = document.getElementById('installBtn');
  const hint = document.getElementById('iosHint');
  if (!btn && !hint) return;

  // --- already installed? hide everything and bail
  const isStandalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: minimal-ui)').matches ||
    window.navigator.standalone === true;
  if (isStandalone) {
    if (btn) btn.hidden = true;
    if (hint) hint.hidden = true;
    return;
  }

  // --- iOS Safari path (no beforeinstallprompt API)
  const ua = window.navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
  const isIOSSafari = isIOS && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
  if (isIOSSafari && hint) {
    hint.hidden = false;
    hint.innerHTML =
      'To install: tap the <strong>Share</strong> icon ' +
      '<span aria-hidden="true">&#x2B06;&#xFE0F;</span> ' +
      'in Safari, then <strong>Add to Home Screen</strong>.';
  }

  // --- standard PWA install path
  let deferred = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferred = e;
    if (btn) btn.hidden = false;
  });

  if (btn) {
    btn.addEventListener('click', async () => {
      if (!deferred) {
        // browser hasn't fired beforeinstallprompt yet
        alert(
          'Your browser will offer to install Auguspay automatically after a few seconds. ' +
          'Look for an "Install" icon in the address bar, or use the browser menu -> "Install app".'
        );
        return;
      }
      btn.disabled = true;
      try {
        await deferred.prompt();
        const choice = await deferred.userChoice;
        if (choice.outcome === 'accepted') {
          btn.hidden = true;
        }
      } finally {
        deferred = null;
        btn.disabled = false;
      }
    });
  }

  window.addEventListener('appinstalled', () => {
    if (btn) btn.hidden = true;
    if (hint) hint.hidden = true;
  });
})();


