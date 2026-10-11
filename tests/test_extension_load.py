"""Real extension load test: launches Chromium with the unpacked MV3 extension,
verifies the service worker registers, and exercises the popup against a live
stub API.

Run:  .venv/bin/python -m pytest tests/test_extension_load.py -q -s
Requires: playwright + chromium (headed; WSLg display).
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

# This test needs a real display + browser and is opt-in, so it does not break
# the default suite. Run it with:  RUN_EXTENSION_TESTS=1 pytest tests/test_extension_load.py
if not os.environ.get("RUN_EXTENSION_TESTS"):
    pytest.skip(
        "extension load test is opt-in; set RUN_EXTENSION_TESTS=1 to run",
        allow_module_level=True,
    )

EXT_DIR = Path(__file__).resolve().parent.parent / "extension"


class _StubHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/v1/health"):
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": {"code": "NOT_FOUND", "message": "no"}})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/api/v1/generate"):
            self._json(200, {
                "hashtags": [{"tag": "#ai", "score": 0.9, "trending": True, "source": "trend"}],
                "platform": "x", "max_tags": 5, "generation_id": "t1", "model": "stub",
            })
        else:
            self._json(404, {"error": {"code": "NOT_FOUND", "message": "no"}})


@pytest.fixture(scope="module")
def stub_api():
    with socketserver.TCPServer(("127.0.0.1", 8123), _StubHandler) as srv:
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        yield "http://127.0.0.1:8123"
        srv.shutdown()


def test_extension_loads_and_service_worker_registers(stub_api):
    from playwright.sync_api import sync_playwright

    assert EXT_DIR.exists(), f"extension dir missing: {EXT_DIR}"
    user_data = "/home/hermes/.hermes/cache/scratch/pw-ext-profile"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data,
            headless=False,
            args=[
                f"--disable-extensions-except={EXT_DIR}",
                f"--load-extension={EXT_DIR}",
                "--no-first-run",
            ],
        )
        try:
            # 1. Service worker must register (proves the extension loaded).
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event(
                "serviceworker", timeout=15000
            )
            ext_id = sw.url.split("/")[2]
            print(f"\n[ext] service worker registered: {sw.url}")

            # 2. Point the extension at the stub API and drive the popup.
            popup = ctx.new_page()
            popup.goto(f"chrome-extension://{ext_id}/popup.html")
            popup.wait_for_load_state("domcontentloaded")

            # The popup should render its UI elements.
            assert popup.query_selector("#go") is not None, "popup missing #go button"
            assert popup.query_selector("#text") is not None, "popup missing #text"

            # 3. Set the API base to the stub and call the service worker's
            #    GENERATE path directly (no content script on a blank page).
            result = popup.evaluate(
                """(api) => new Promise((resolve) => {
                    chrome.storage.local.set({ apiBase: api }, () => {
                        chrome.runtime.sendMessage(
                            { type: 'GENERATE', payload: { text: 'hello world', platform: 'x' } },
                            (resp) => resolve(resp)
                        );
                    });
                })""",
                stub_api,
            )
            print(f"[ext] GENERATE response: {result}")
            assert result and result.get("ok"), f"generate failed: {result}"
            assert result["data"]["hashtags"][0]["tag"] == "#ai"
        finally:
            ctx.close()
