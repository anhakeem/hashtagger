// Hashtagger — service worker (MV3).
//
// Owns ALL network calls (the content script never calls the API directly, so
// host permissions stay minimal and CORS is never an issue). State lives in
// chrome.storage because the service worker is terminated when idle.

const DEFAULT_API = "http://localhost:8000";

async function getApiBase() {
  const { apiBase } = await chrome.storage.local.get(["apiBase"]);
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

// Message router. Listeners registered at top level so they exist on cold start.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
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
