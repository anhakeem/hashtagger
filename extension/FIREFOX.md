# Firefox build

Firefox 109+ supports Manifest V3, but with differences from Chrome:

| Chrome | Firefox |
|--------|---------|
| `background.service_worker` (module) | `background.scripts` (array, event page) |
| `chrome.*` only | `browser.*` (promises) + `chrome.*` alias |
| `action` | `action` (supported in MV3) |

## Build the Firefox variant

The Firefox manifest (`manifest.firefox.json`) differs from Chrome's
(`manifest.json`). To load it, swap the manifest:

```bash
cd extension
cp manifest.json manifest.chrome.json.bak   # keep the chrome one
cp manifest.firefox.json manifest.json
# ... load unpacked in Firefox ...
# restore afterwards:
mv manifest.chrome.json.bak manifest.json
```

> A cleaner build step (a small script that assembles `dist/firefox/` and
> `dist/chrome/` from a shared source + per-browser manifest) is the natural
> next increment — see the note at the bottom.

## Load in Firefox (temporary)

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on…**
3. Select `extension/manifest.json` (after swapping to the Firefox variant)

The temporary add-on lasts until Firefox restarts. For a permanent install you
need it signed via [addons.mozilla.org](https://addons.mozilla.org).

## How the code stays compatible

`browser-compat.js` is loaded **before** the other scripts in the Firefox build
and exposes an `ext` helper with promise-based `storageGet`/`storageSet`/
`sendMessage`/`sendToTab`. Chrome's callback style and Firefox's promise style
both go through it, so the rest of the code is written once.
