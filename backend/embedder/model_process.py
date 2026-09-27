from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import numpy as np
from onnx_model import MODEL_KEY, OnnxEncoder


def main() -> None:
    replies = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    encoder = OnnxEncoder(
        Path(os.environ.get("EMBEDDER_MODEL_DIR", "/models")),
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    print(json.dumps({"model": MODEL_KEY, "device": encoder.device}), file=replies, flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        vectors = encoder.encode(request["texts"], query=request["query"])
        payload = base64.b64encode(np.asarray(vectors, dtype="<f4").tobytes()).decode()
        print(json.dumps({"vectors": payload}), file=replies, flush=True)


if __name__ == "__main__":
    main()
