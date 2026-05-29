from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_TEXTS = 256
IDLE_SECONDS = float(os.environ.get("EMBEDDER_IDLE_SECONDS", "600"))
MODEL_PROCESS = Path(__file__).with_name("model_process.py")


class ModelProcessError(RuntimeError):
    pass


class Model:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process: subprocess.Popen[bytes] | None = None
        self.last_used = time.monotonic()
        self.model = ""
        self.device = ""

    def load(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self.process = subprocess.Popen(
            [sys.executable, str(MODEL_PROCESS)], stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        ready = self._read()
        self.model, self.device = ready["model"], ready["device"]
        self.last_used = time.monotonic()

    def embed(self, texts: list[str], *, query: bool) -> str:
        with self.lock:
            try:
                self.load()
                assert self.process is not None and self.process.stdin is not None
                self.process.stdin.write(json.dumps({"texts": texts, "query": query}).encode())
                self.process.stdin.write(b"\n")
                self.process.stdin.flush()
                vectors = self._read()["vectors"]
            except (OSError, ValueError, KeyError, ModelProcessError):
                self._stop()
                raise ModelProcessError("The model process failed") from None
            self.last_used = time.monotonic()
            return vectors

    def stop_when_idle(self) -> None:
        while True:
            time.sleep(min(30.0, IDLE_SECONDS))
            with self.lock:
                if self.process is not None and time.monotonic() - self.last_used >= IDLE_SECONDS:
                    self._stop()
                    print(f"Unloaded the model after {IDLE_SECONDS:.0f} idle seconds", flush=True)

    def _read(self) -> dict[str, str]:
        assert self.process is not None and self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            raise ModelProcessError("The model process exited")
        return json.loads(line)

    def _stop(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


model = Model()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path != "/health":
            self._send(404, {"error": "not found"})
            return
        self._send(200, {"model": model.model, "device": model.device})

    def do_POST(self) -> None:
        if self.path != "/embed":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY_BYTES:
            self._send(413, {"error": "request body too large or empty"})
            return
        try:
            request = json.loads(self.rfile.read(length))
            texts = request["texts"]
            query = request.get("query", False)
            if (
                not isinstance(texts, list)
                or len(texts) > MAX_TEXTS
                or not all(isinstance(text, str) for text in texts)
                or not isinstance(query, bool)
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            self._send(400, {"error": "expected {texts: [str], query: bool}"})
            return
        try:
            vectors = model.embed(texts, query=query)
        except ModelProcessError as error:
            self._send(503, {"error": str(error)})
            return
        self._send(200, {"model": model.model, "device": model.device, "vectors": vectors})

    def log_message(self, format: str, *args: object) -> None: ...


if __name__ == "__main__":
    model.load()
    print(f"Embedding with {model.model} on {model.device}", flush=True)
    threading.Thread(target=model.stop_when_idle, daemon=True).start()
    port = int(os.environ.get("EMBEDDER_PORT", "8100"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
