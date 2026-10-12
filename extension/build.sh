#!/usr/bin/env bash
# Build per-browser extension bundles from one shared source tree.
#
# The extension source lives in extension/ with two manifests:
#   manifest.json          -> Chrome/Edge/Brave (MV3, service_worker)
#   manifest.firefox.json  -> Firefox 109+ (MV3, background.scripts)
#
# This script assembles dist/chrome/ and dist/firefox/, each with the right
# manifest copied to manifest.json, so you can load either bundle unpacked
# without hand-swapping manifests.
#
# Usage:  ./build.sh          # build both
#         ./build.sh chrome   # build one
set -euo pipefail

cd "$(dirname "$0")"
SRC="."
DIST="dist"
TARGET="${1:-all}"

# Files shared by both builds (everything except manifests, dist, and tooling).
SHARED=(
  background.js content.js popup.js popup.html browser-compat.js
  icons
)

build_one() {
  local name="$1" manifest="$2"
  local out="$DIST/$name"
  rm -rf "$out"
  mkdir -p "$out"

  for item in "${SHARED[@]}"; do
    if [ -e "$SRC/$item" ]; then
      cp -R "$SRC/$item" "$out/"
    else
      echo "  ! missing: $item" >&2
    fi
  done
  cp "$SRC/$manifest" "$out/manifest.json"

  # Sanity-check: every referenced file exists in the bundle.
  python3 - "$out" <<'PY'
import json, os, sys
out = sys.argv[1]
m = json.load(open(os.path.join(out, "manifest.json")))
refs = [m["action"]["default_popup"]]
bg = m.get("background", {})
refs += [bg["service_worker"]] if "service_worker" in bg else bg.get("scripts", [])
for cs in m.get("content_scripts", []):
    refs += cs.get("js", [])
refs += list(m.get("icons", {}).values())
missing = [r for r in refs if not os.path.exists(os.path.join(out, r))]
if missing:
    print(f"  ! {out}: missing {missing}", file=sys.stderr)
    sys.exit(1)
print(f"  ✓ {out} ({len(refs)} files referenced, all present)")
PY
}

echo "Building extension bundles..."
case "$TARGET" in
  chrome)  build_one chrome  manifest.json ;;
  firefox) build_one firefox manifest.firefox.json ;;
  all)     build_one chrome manifest.json; build_one firefox manifest.firefox.json ;;
  *) echo "usage: $0 [all|chrome|firefox]" >&2; exit 2 ;;
esac
echo "Done. Load dist/chrome or dist/firefox as an unpacked extension."
