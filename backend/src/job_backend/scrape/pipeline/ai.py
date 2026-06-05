import hashlib
import json

import httpx2

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.constants import PROMPT_VERSION, SYSTEM_PROMPT
from job_backend.scrape.pipeline.models import ExtractionResult, RawDocument


class AiNormalizer:
    def __init__(self, settings: AiSettings, transport: httpx2.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._client: httpx2.Client | None = None
        self.usage = AiUsageTracker(settings)

    def open(self) -> None:
        if self._client is None:
            self._client = httpx2.Client(
                transport=self._transport,
                timeout=self.settings.timeout_seconds,
            )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def cache_key(self) -> str:
        value = [
            self.settings.base_url,
            self.settings.model,
            self.settings.response_format,
            self.settings.temperature,
            self.settings.max_output_tokens,
            self.settings.temperature,
            self.settings.max_output_tokens,
            PROMPT_VERSION,
            SYSTEM_PROMPT,
            ExtractionResult.model_json_schema(),
        ]
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    @property
    def max_calls_per_scrape(self) -> int:
        return self.settings.max_calls_per_scrape

    def extract(self, document: RawDocument) -> ExtractionResult:
        if len(document.content) > self.settings.max_document_chars:
            raise SourceDataError("Document exceeds JOB_AI_MAX_DOCUMENT_CHARS; split it first")
        user = json.dumps(document.model_dump(mode="json"), ensure_ascii=False)
        try:
            return complete_json(
                self.settings,
                system_prompt=SYSTEM_PROMPT,
                user_content=user,
                response_model=ExtractionResult,
                schema_name="job_extraction",
                transport=self._transport,
                client=self._client,
                on_usage=self.usage.record,
            )
        except AiCompletionError as error:
            raise SourceDataError(str(error)) from None
