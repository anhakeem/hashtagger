# Firefox build

Firefox 109+ supports Manifest V3, but with differences from Chrome:

| Chrome | Firefox |
|--------|---------|
| `background.service_worker` (module) | `background.scripts` (array, event page) |
| `chrome.*` only | `browser.*` (promises) + `chrome.*` alias |
| `action` | `action` (supported in MV3) |

## Build the Firefox variant

The build script assembles both bundles from one source tree:

```bash
cd extension
./build.sh            # builds dist/chrome/ and dist/firefox/
./build.sh firefox    # or just one
```

Each bundle gets the right manifest copied to `manifest.json`, and the script
verifies every file the manifest references actually exists. Then:

- **Chrome/Edge/Brave:** load `dist/chrome/` unpacked
- **Firefox:** load `dist/firefox/` via `about:debugging#/runtime/this-firefox`

`dist/` is git-ignored — it is generated output, not source.

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
