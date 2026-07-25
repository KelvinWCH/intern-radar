import base64
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx2
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from job_backend.common.logger import get_logger
from job_backend.matching.onnx_model import (
    DIMENSIONS,
    MODEL_KEY,
    OnnxEncoder,
    download_model,
    model_ready,
)

logger = get_logger(__name__)

EMBEDDER_URL_ENV = "JOB_EMBEDDER_URL"
MODEL_DIR_ENV = "JOB_EMBEDDING_MODEL_DIR"
REMOTE_TIMEOUT_SECONDS = 120.0
SIDECAR_RETRY_SECONDS = 600.0


class Embedder(Protocol):
    model: str
    device: str

    def embed(self, texts: list[str], *, query: bool) -> NDArray[np.float32]: ...


def encode_vector(vector: NDArray[np.float32]) -> str:
    return base64.b64encode(np.asarray(vector, dtype="<f2").tobytes()).decode()


def decode_vector(value: str) -> NDArray[np.float32]:
    raw = base64.b64decode(value, validate=True)
    if len(raw) != DIMENSIONS * 2:
        raise ValueError("Stored vector has the wrong size")
    return np.ndarray((DIMENSIONS,), dtype=np.dtype("<f2"), buffer=raw).astype(np.float32)


class LocalEmbedder:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.model = MODEL_KEY
        self.device = "cpu"
        self._encoder: OnnxEncoder | None = None

    def embed(self, texts: list[str], *, query: bool) -> NDArray[np.float32]:
        if self._encoder is None:
            if not model_ready(self.directory):
                logger.info("Downloading the %s embedding model", MODEL_KEY)
                download_model(self.directory)
            self._encoder = OnnxEncoder(self.directory, ["CPUExecutionProvider"])
        return self._encoder.encode(texts, query=query)


class _EmbedResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    model: str
    device: str
    vectors: str = Field(description="Base64 little-endian float32 rows.")


class _Health(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    model: str
    device: str


class RemoteEmbedder:
    def __init__(self, url: str, *, transport: httpx2.BaseTransport | None = None) -> None:
        self.client = httpx2.Client(
            base_url=url.rstrip("/"), timeout=REMOTE_TIMEOUT_SECONDS, transport=transport
        )
        response = self.client.get("/health")
        response.raise_for_status()
        health = _Health.model_validate_json(response.content)
        if health.model != MODEL_KEY:
            raise ValueError(f"Embedding sidecar runs {health.model}, expected {MODEL_KEY}")
        self.model = health.model
        self.device = health.device

    def embed(self, texts: list[str], *, query: bool) -> NDArray[np.float32]:
        response = self.client.post("/embed", json={"texts": texts, "query": query})
        response.raise_for_status()
        body = _EmbedResponse.model_validate_json(response.content)
        raw = base64.b64decode(body.vectors, validate=True)
        if body.model != self.model or len(raw) != len(texts) * DIMENSIONS * 4:
            raise ValueError("Embedding sidecar returned an unexpected response")
        self.device = body.device
        shape = (len(texts), DIMENSIONS)
        return np.ndarray(shape, dtype=np.dtype("<f4"), buffer=raw).astype(np.float32)


def model_directory(data_directory: Path) -> Path:
    configured = os.environ.get(MODEL_DIR_ENV, "").strip()
    if configured:
        return Path(configured)
    return data_directory / "models" / MODEL_KEY.replace("/", "-")


class PreferredEmbedder:
    def __init__(
        self,
        url: str,
        local: Embedder,
        *,
        connect: Callable[[str], Embedder] = RemoteEmbedder,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.local = local
        self.connect = connect
        self.clock = clock
        self.model = MODEL_KEY
        self.device = "cpu"
        self._remote: Embedder | None = None
        self._retry_at = 0.0

    def embed(self, texts: list[str], *, query: bool) -> NDArray[np.float32]:
        if self._remote is None and self.clock() >= self._retry_at:
            try:
                self._remote = self.connect(self.url)
            except (httpx2.HTTPError, ValueError) as error:
                logger.warning("Embedding sidecar unavailable, using the CPU instead: %s", error)
                self._retry_at = self.clock() + SIDECAR_RETRY_SECONDS
        if self._remote is not None:
            try:
                vectors = self._remote.embed(texts, query=query)
                self.device = self._remote.device
                return vectors
            except (httpx2.HTTPError, ValueError) as error:
                logger.warning("Embedding sidecar failed, using the CPU instead: %s", error)
                self._remote = None
                self._retry_at = self.clock() + SIDECAR_RETRY_SECONDS
        self.device = self.local.device
        return self.local.embed(texts, query=query)


def embedder_from_environment(data_directory: Path) -> Embedder:
    local = LocalEmbedder(model_directory(data_directory))
    url = os.environ.get(EMBEDDER_URL_ENV, "").strip()
    return PreferredEmbedder(url, local) if url else local
