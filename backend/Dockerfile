# works on arm64 and x86-64
FROM python:3.12-slim-bookworm AS tectonic

# tectonic for the pdf export, checked against a pinned sha256
RUN python - <<'PY'
import hashlib
import io
import platform
import tarfile
import urllib.request
from pathlib import Path

targets = {
    "aarch64": ("aarch64", "b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8"),
    "x86_64": ("x86_64", "8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7"),
}
target, digest = targets[platform.machine()]
url = (
    "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/"
    f"tectonic-0.17.0-{target}-unknown-linux-musl.tar.gz"
)
with urllib.request.urlopen(url, timeout=120) as response:
    payload = response.read()
if hashlib.sha256(payload).hexdigest() != digest:
    raise RuntimeError("Tectonic release checksum mismatch")
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
    binary = archive.extractfile("tectonic")
    if binary is None:
        raise RuntimeError("Tectonic release has no executable")
    destination = Path("/usr/local/bin/tectonic")
    destination.write_bytes(binary.read())
    destination.chmod(0o755)
PY

RUN tectonic --version

# just the dependency list so editing tool settings doesnt bust the cache
FROM python:3.12-slim-bookworm AS requirements
COPY pyproject.toml /pyproject.toml
RUN python -c "import tomllib; print(*tomllib.load(open('/pyproject.toml', 'rb'))['project']['dependencies'], sep='\n')" \
    > /requirements.txt

FROM python:3.12-slim-bookworm

ARG PLAYWRIGHT_VERSION=1.64.0
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    JOB_DATA_DIR=/data \
    JOB_BROWSER_HEADLESS=true

WORKDIR /app
# slow layers first, a code change only rebuilds the last few mb
RUN python -m pip install --no-cache-dir "playwright==${PLAYWRIGHT_VERSION}" \
    && python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 worker \
    && useradd --uid 10001 --gid worker --create-home worker \
    && mkdir /data \
    && chown worker:worker /data \
    && chmod -R a+rX /ms-playwright

COPY --from=requirements /requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt "playwright==${PLAYWRIGHT_VERSION}"

COPY --from=tectonic /usr/local/bin/tectonic /usr/local/bin/tectonic

COPY pyproject.toml ./pyproject.toml
COPY src/job_backend ./src/job_backend
RUN python -m pip install --no-cache-dir --no-deps .

# chromium keeps its sandbox, compose passes the seccomp profile
USER worker
ENTRYPOINT ["python", "-m", "job_backend.scrape.worker"]
