#!/usr/bin/env python3
"""Minimal Telegram Bot API mock for local environment demos.

Implements the endpoints python-telegram-bot hits during polling:
getMe, deleteWebhook, getUpdates. Optional sendMessage for command tests.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


BOT_USER = {
    "id": 1234567890,
    "is_bot": True,
    "first_name": "FiveGuysDevBot",
    "username": "five_guys_dev_bot",
    "can_join_groups": True,
    "can_read_all_group_messages": True,
    "supports_inline_queries": False,
}


class TelegramMockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    update_offset = 0

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[mock-telegram] {self.address_string()} - {fmt % args}")

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        content_type = (self.headers.get("Content-Type") or "").lower()
        text = raw.decode("utf-8", errors="replace")
        if "application/json" in content_type:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {}
        # python-telegram-bot often posts form-encoded fields
        from urllib.parse import parse_qs

        parsed = parse_qs(text, keep_blank_values=True)
        flat = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        # Coerce numeric fields commonly used by Bot API
        for key in ("timeout", "offset", "limit", "chat_id", "message_id"):
            if key in flat and isinstance(flat[key], str) and flat[key].lstrip("-").isdigit():
                flat[key] = int(flat[key])
        return flat

    def _ok(self, result):
        body = json.dumps({"ok": True, "result": result}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, status: int, description: str):
        body = json.dumps({"ok": False, "description": description}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        # Expected: /bot<token>/<method>
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 or not parts[0].startswith("bot"):
            self._fail(404, "Not Found")
            return

        method = parts[1]
        payload = self._read_payload()

        if method == "getMe":
            self._ok(BOT_USER)
            return
        if method == "deleteWebhook":
            self._ok(True)
            return
        if method == "getUpdates":
            # Honor long-poll timeout (cap for snappy local demos).
            timeout = int(payload.get("timeout", 0) or 0)
            time.sleep(min(max(timeout, 1), 3))
            self._ok([])
            return
        if method == "sendMessage":
            self._ok(
                {
                    "message_id": int(time.time()),
                    "date": int(time.time()),
                    "chat": {
                        "id": payload.get("chat_id", 1),
                        "type": "private",
                    },
                    "text": payload.get("text", ""),
                    "from": BOT_USER,
                }
            )
            return
        if method in {"setMyCommands", "getMyCommands", "logOut", "close"}:
            self._ok(True if method != "getMyCommands" else [])
            return

        # Default success for unimplemented methods so startup isn't blocked.
        self._ok(True)

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path in {"/", "/health"}:
            self._ok({"status": "ok", "service": "mock-telegram"})
            return
        self._fail(404, "Not Found")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), TelegramMockHandler)
    print(f"Mock Telegram API listening on http://{args.host}:{args.port}/bot")
    print("Health check: http://{0}:{1}/health".format(args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down mock Telegram API")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
