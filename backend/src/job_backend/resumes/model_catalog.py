from time import sleep

import httpx2
from pydantic import ValidationError

from job_backend.common.models import AiSettings
from job_backend.resumes.models import ModelCatalog, ProviderModelCatalog

CATALOG_CONNECT_ATTEMPTS = 3
CATALOG_RETRY_SECONDS = 1.0


def read_model_catalog(
    settings: AiSettings, *, transport: httpx2.BaseTransport | None = None
) -> ModelCatalog:
    headers = {"Accept": "application/json"}
    if settings.api_key is not None:
        headers["Authorization"] = "Bearer " + settings.api_key.get_secret_value()
    try:
        catalog = _fetch_catalog(settings.base_url + "/models", headers, transport)
        names = {model.id.strip() for model in catalog.data if model.id.strip()}
        names.add(settings.model)
        return ModelCatalog(models=sorted(names, key=str.casefold))
    except (httpx2.HTTPError, ValidationError, ValueError):
        return ModelCatalog(
            models=[settings.model],
            warning=(
                "Could not load the provider's model list. The configured default is available."
            ),
        )


def _fetch_catalog(
    url: str, headers: dict[str, str], transport: httpx2.BaseTransport | None
) -> ProviderModelCatalog:
    for attempt in range(1, CATALOG_CONNECT_ATTEMPTS + 1):
        try:
            with (
                httpx2.Client(transport=transport, timeout=10) as client,
                client.stream("GET", url, headers=headers) as response,
            ):
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 2 * 1024 * 1024:
                        raise ValueError("Model catalog too large")
                return ProviderModelCatalog.model_validate_json(bytes(data), strict=True)
        except httpx2.ConnectError:
            if attempt == CATALOG_CONNECT_ATTEMPTS:
                raise
            sleep(CATALOG_RETRY_SECONDS * attempt)
    raise RuntimeError("Unreachable catalog state")
