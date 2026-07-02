import base64
import json

import httpx2
import numpy as np
import pytest

from job_backend.matching.embedding import (
    SIDECAR_RETRY_SECONDS,
    PreferredEmbedder,
    RemoteEmbedder,
    decode_vector,
    encode_vector,
)
from job_backend.matching.onnx_model import DIMENSIONS, MODEL_KEY
from tests.matching.helpers import FakeEmbedder


def test_float16_round_trip() -> None:
    vector = np.random.default_rng(1).normal(size=DIMENSIONS).astype(np.float32)
    vector /= np.sqrt(vector @ vector)
    stored = encode_vector(vector)
    assert len(base64.b64decode(stored)) == DIMENSIONS * 2
    assert float(decode_vector(stored) @ vector) > 0.9999
    with pytest.raises(ValueError):
        decode_vector(base64.b64encode(b"\0\0").decode())


def _sidecar(model: str = MODEL_KEY) -> httpx2.MockTransport:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/health":
            return httpx2.Response(200, json={"model": model, "device": "cuda"})
        texts = json.loads(request.content)["texts"]
        vectors = (np.ones((len(texts), DIMENSIONS)) / np.sqrt(DIMENSIONS)).astype("<f4")
        return httpx2.Response(
            200,
            json={
                "model": model,
                "device": "cuda",
                "vectors": base64.b64encode(vectors.tobytes()).decode(),
            },
        )

    return httpx2.MockTransport(respond)


def test_sidecar_falls_back_to_cpu() -> None:
    now = [0.0]
    attempts: list[str] = []
    local = FakeEmbedder()
    local.device = "cpu"

    def connect(url: str) -> RemoteEmbedder:
        attempts.append(url)
        if len(attempts) == 1:
            raise httpx2.ConnectError("refused")
        return RemoteEmbedder(url, transport=_sidecar())

    preferred = PreferredEmbedder(
        "http://embedder:8100", local, connect=connect, clock=lambda: now[0]
    )
    preferred.embed(["a"], query=False)
    preferred.embed(["b"], query=False)
    assert preferred.device == "cpu" and len(attempts) == 1 and local.calls == 2
    now[0] = SIDECAR_RETRY_SECONDS
    preferred.embed(["c"], query=False)
    assert preferred.device == "cuda" and len(attempts) == 2 and local.calls == 2
