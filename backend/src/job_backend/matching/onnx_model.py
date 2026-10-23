from __future__ import annotations

import hashlib
import importlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray
from tokenizers import Tokenizer

MODEL_NAME = "bge-small-en-v1.5"
MODEL_REPOSITORY = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
MODEL_FILES = (
    (
        "onnx/model.onnx",
        "model.onnx",
        "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
    ),
    (
        "tokenizer.json",
        "tokenizer.json",
        "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    ),
)
MAX_TOKENS = 512
DIMENSIONS = 384
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MODEL_KEY = f"{MODEL_NAME}@{MODEL_REVISION[:7]}/{MAX_TOKENS}"
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024


class _Encoding(Protocol):
    @property
    def ids(self) -> list[int]: ...

    @property
    def attention_mask(self) -> list[int]: ...


class _Tokenizer(Protocol):
    def enable_truncation(self, max_length: int) -> None: ...

    def enable_padding(self, *, pad_id: int, pad_token: str) -> None: ...

    def encode_batch(self, input: list[str]) -> list[_Encoding]: ...


class _Session(Protocol):
    def run(
        self, output_names: None, input_feed: dict[str, NDArray[np.int64]]
    ) -> list[NDArray[np.float32]]: ...

    def get_providers(self) -> list[str]: ...


def model_ready(directory: Path) -> bool:
    return all((directory / name).is_file() for _path, name, _digest in MODEL_FILES)


def download_model(directory: Path, *, timeout: float = 300.0) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path, name, digest in MODEL_FILES:
        target = directory / name
        if target.is_file():
            continue
        url = f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{path}"
        handle, temporary = tempfile.mkstemp(dir=directory, prefix=f".{name}.")
        try:
            hasher = hashlib.sha256()
            size = 0
            with (
                os.fdopen(handle, "wb") as output,
                urllib.request.urlopen(url, timeout=timeout) as response,
            ):
                while chunk := response.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise OSError(f"{name} exceeded the model download size limit")
                    hasher.update(chunk)
                    output.write(chunk)
            if hasher.hexdigest() != digest:
                raise OSError(f"{name} does not match its pinned checksum")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class OnnxEncoder:
    def __init__(self, directory: Path, providers: list[str], *, threads: int = 0) -> None:
        runtime = importlib.import_module("onnxruntime")
        options = runtime.SessionOptions()
        options.intra_op_num_threads = threads
        self.session = cast(
            _Session,
            runtime.InferenceSession(str(directory / "model.onnx"), options, providers=providers),
        )
        self.tokenizer = cast(_Tokenizer, Tokenizer.from_file(str(directory / "tokenizer.json")))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

    @property
    def device(self) -> str:
        return "cuda" if "CUDAExecutionProvider" in self.session.get_providers() else "cpu"

    def encode(self, texts: list[str], *, query: bool) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, DIMENSIONS), dtype=np.float32)
        encodings = self.tokenizer.encode_batch(
            [QUERY_PREFIX + text if query else text for text in texts]
        )
        ids = np.asarray([encoding.ids for encoding in encodings], dtype=np.int64)
        mask = np.asarray([encoding.attention_mask for encoding in encodings], dtype=np.int64)
        output = self.session.run(
            None, {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        )[0]
        vectors = np.asarray(output[:, 0, :], dtype=np.float32)
        norms = np.sqrt(np.sum(vectors * vectors, axis=1, keepdims=True))
        return np.asarray(vectors / np.maximum(norms, 1e-12), dtype=np.float32)
