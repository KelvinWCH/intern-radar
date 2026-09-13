import gzip
import json
from io import BytesIO
from urllib.request import Request, urlopen

from job_backend.auth.sessions import Authenticator


def check_compression(url: str = "http://127.0.0.1:8000/openapi.json") -> None:
    headers = {"Accept-Encoding": "gzip"}
    authenticator = Authenticator.from_environment()
    if authenticator is not None:
        headers["Authorization"] = "Bearer " + authenticator.issue(lifetime=60)[0]
    request = Request(url, headers=headers)
    with urlopen(request, timeout=10) as response:
        if response.headers.get("Content-Encoding", "").lower() != "gzip":
            raise RuntimeError("API did not negotiate gzip for its OpenAPI response")
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise RuntimeError("Compressed API schema exceeds the smoke-check size limit")
    with gzip.GzipFile(fileobj=BytesIO(body)) as stream:
        decoded = stream.read(4_000_001)
    if len(decoded) > 4_000_000 or not isinstance(json.loads(decoded), dict):
        raise RuntimeError("Invalid compressed API schema")


if __name__ == "__main__":
    check_compression()
    print("API gzip negotiation passed.")
