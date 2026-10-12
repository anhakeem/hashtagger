// Hashtagger — service worker / background script (MV3).
//
// Owns ALL network calls (the content script never calls the API directly, so
// host permissions stay minimal and CORS is never an issue). State lives in
// extension storage because the worker is terminated when idle.
//
// Cross-browser: uses `ext.*` from browser-compat.js. Chrome loads it via the
// importScripts call below; Firefox loads it via the manifest.

if (typeof importScripts === "function") {
  importScripts("browser-compat.js");
}

const DEFAULT_API = "http://localhost:8000";

async function getApiBase() {
  const { apiBase } = await ext.storageGet(["apiBase"]);
  return apiBase || DEFAULT_API;
}

async function generateHashtags({ text, platform, maxTags, tone }) {
  const api = await getApiBase();
  const body = { text, platform };
  if (maxTags) body.max_tags = maxTags;
  if (tone) body.tone = tone;

  const resp = await fetch(`${api}/api/v1/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data?.error?.message || `Request failed (${resp.status})`);
  }
  return data;
}

// Listener registered at top level so it exists on cold start.
ext.onMessage((msg, _sender, sendResponse) => {
  if (msg?.type === "GENERATE") {
    generateHashtags(msg.payload)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true; // async response
  }
  if (msg?.type === "HEALTH") {
    getApiBase()
      .then((api) => fetch(`${api}/api/v1/health`))
      .then((r) => sendResponse({ ok: r.ok }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  return false;
});
