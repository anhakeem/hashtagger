# Hashtagger — Chrome Extension (Manifest V3)

Get ranked, trending hashtags for your post, right in the X/Twitter composer.

## Install (unpacked, for development)

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** and select this `extension/` directory
4. Pin the Hashtagger icon

## Requirements

The extension talks to the Hashtagger API. Run it locally first:

```bash
cd ..                        # repo root
.venv/bin/uvicorn hashtagger.api.main:app --reload --port 8000
# or, if installed as a package:
# uvicorn hashtagger.api.main:app --reload
```

The API base defaults to `http://localhost:8000`. To point at a different host,
set it in the popup or via `chrome.storage.local`:

```js
chrome.storage.local.set({ apiBase: "https://api.yourdomain.com" });
```

> When you change `apiBase`, also add that origin to `host_permissions` in
> `manifest.json` and reload the extension.

## How it works

```
┌──────────────┐  GET_COMPOSER_TEXT   ┌───────────────┐
│  popup.js    │ ───────────────────► │  content.js   │  (reads x.com composer)
│              │ ◄─────────────────── │               │
│              │      { text }        └───────────────┘
│              │
│              │  GENERATE            ┌────────────────┐   POST /api/v1/generate
│              │ ───────────────────► │ background.js  │ ──────────────────────► API
│              │ ◄─────────────────── │ (service worker)│ ◄──────────────────────
└──────────────┘   { hashtags }       └────────────────┘
```

- **`background.js`** (service worker) owns every network call. The content
  script never calls the API, so CORS is a non-issue and host permissions stay
  minimal. State lives in `chrome.storage` because the worker is terminated
  when idle.
- **`content.js`** reads the composer text on demand. It is deliberately
  minimal — it touches only the composer element.
- **`popup.js`** drives the UI: capture the post, generate, copy the tags.

## Permissions

| Permission | Why |
|-----------|-----|
| `storage` | Persist the API base + survive service-worker restarts |
| `activeTab` | Read the current tab only when the user acts |
| `host_permissions: http://localhost:8000/*` | Call the local API |

No `<all_urls>`, no remote code, no page-content access beyond the composer.

## Files

```
extension/
├── manifest.json     # MV3 manifest
├── background.js     # service worker — all network calls
├── content.js        # reads the X/Twitter composer
├── popup.html/.js    # the popup UI
└── icons/            # 16/48/128 png
```
