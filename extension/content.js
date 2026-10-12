// Hashtagger — content script (runs on x.com / twitter.com).
//
// Reads the composer text when asked. Deliberately minimal: it does NOT call
// the API (the service worker does), and it only touches the composer element.
//
// Cross-browser: uses `ext.onMessage` from browser-compat.js (loaded before
// this file by the manifest in both Chrome and Firefox).

const COMPOSER_SELECTORS = [
  'div[data-testid="tweetTextarea_0"]',
  'div[role="textbox"][data-testid="tweetTextarea_0"]',
  'div[contenteditable="true"][role="textbox"]',
];

function findComposer() {
  for (const sel of COMPOSER_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

function readComposerText() {
  const el = findComposer();
  if (!el) return "";
  // innerText preserves line breaks better than textContent for contenteditable.
  return (el.innerText || el.textContent || "").trim();
}

ext.onMessage((msg, _sender, sendResponse) => {
  if (msg?.type === "GET_COMPOSER_TEXT") {
    sendResponse({ text: readComposerText() });
  }
  return false;
});
