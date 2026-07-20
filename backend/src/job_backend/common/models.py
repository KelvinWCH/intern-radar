import os
import re
from dataclasses import dataclass, field
from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StringConstraints,
    field_validator,
)

from job_backend.common.environment import load_environment
from job_backend.persistence.models import StoredRecord


class CompletionErrorDetails(BaseModel):
    param: str | None = None


class CompletionErrorResponse(BaseModel):
    error: CompletionErrorDetails


class CompletionMessage(BaseModel):
    content: str | None = None
    refusal: str | None = None


class CompletionChoice(BaseModel):
    message: CompletionMessage
    finish_reason: str


class CompletionUsage(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)


class CompletionResponse(BaseModel):
    choices: list[CompletionChoice]
    usage: CompletionUsage | None = None


class CompletionDelta(CompletionMessage):
    reasoning_content: str | None = None
    reasoning: str | None = None


class CompletionDeltaChoice(BaseModel):
    index: int = Field(ge=0)
    delta: CompletionDelta
    finish_reason: str | None = None


class CompletionChunk(BaseModel):
    choices: list[CompletionDeltaChoice]
    usage: CompletionUsage | None = None


class CompletionOutput(BaseModel):
    request_id: str
    text: str
    reasoning: str = ""
    schema_name: str = ""


class ResponsesUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ResponsesIncompleteDetails(BaseModel):
    reason: str | None = None


class ResponsesError(BaseModel):
    message: str | None = None


class ResponsesContent(BaseModel):
    type: str
    text: str | None = None
    refusal: str | None = None


class ResponsesOutputItem(BaseModel):
    type: str
    content: list[ResponsesContent] = Field(default_factory=list[ResponsesContent])


class ResponsesBody(BaseModel):
    status: str | None = None
    output: list[ResponsesOutputItem] = Field(default_factory=list[ResponsesOutputItem])
    usage: ResponsesUsage | None = None
    incomplete_details: ResponsesIncompleteDetails | None = None
    error: ResponsesError | None = None


class ResponsesEvent(BaseModel):
    type: str
    delta: str | None = None
    response: ResponsesBody | None = None
    message: str | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", from_attributes=True)


@dataclass(kw_only=True)
class LogEntry(StoredRecord):
    collection: ClassVar[str] = "application_logs"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    created_at: float = 0.0
    level: str = ""
    logger: str = ""
    message: str = ""
    exception: str | None = None
    pathname: str = ""
    line_number: int = 0
    process_id: int | None = None
    thread_name: str | None = None
    context: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])


ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
AiProvider = Literal["endpoint"]


class AiSettings(StrictModel):
    base_url: str
    model: str = Field(min_length=1)
    api_key: SecretStr | None = None
    provider: AiProvider = "endpoint"
    api: Literal["chat_completions", "responses"] = "chat_completions"
    reasoning_summary: Literal["auto", "concise", "detailed"] | None = None
    response_format: Literal["json_schema", "json_object", "text"] = "json_schema"
    timeout_seconds: float = Field(default=300.0, gt=0, le=600)
    max_document_chars: int = Field(default=500000, gt=0)
    max_calls_per_scrape: int = Field(default=100, gt=0)
    concurrency: int = Field(default=3, ge=1, le=16)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    reasoning_effort: ReasoningEffort | None = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 200:
            raise ValueError("Use a model name between 1 and 200 characters")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Use an HTTP base URL without credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls) -> "AiSettings":
        load_environment()
        base_url = os.environ.get("JOB_AI_BASE_URL")
        model = os.environ.get("JOB_AI_MODEL")
        if not base_url or not model:
            raise ValueError("Set JOB_AI_BASE_URL and JOB_AI_MODEL before using AI features")
        key = os.environ.get("JOB_AI_API_KEY")
        if urlsplit(base_url).hostname == "api.openai.com" and not key:
            raise ValueError("Set JOB_AI_API_KEY in backend/.env before using OpenAI")
        return cls.model_validate(
            {
                "base_url": base_url,
                "model": model,
                "api_key": SecretStr(key) if key else None,
                "provider": os.environ.get("JOB_AI_PROVIDER") or "endpoint",
                "api": os.environ.get("JOB_AI_API") or "chat_completions",
                "reasoning_summary": os.environ.get("JOB_AI_REASONING_SUMMARY") or None,
                "response_format": os.environ.get("JOB_AI_RESPONSE_FORMAT", "json_schema"),
                "timeout_seconds": float(os.environ.get("JOB_AI_TIMEOUT_SECONDS", "300")),
                "max_document_chars": int(os.environ.get("JOB_AI_MAX_DOCUMENT_CHARS", "500000")),
                "max_calls_per_scrape": int(os.environ.get("JOB_AI_MAX_CALLS_PER_IMPORT", "100")),
                "concurrency": int(os.environ.get("JOB_AI_CONCURRENCY", "3")),
                "temperature": _optional_float("JOB_AI_TEMPERATURE"),
                "max_output_tokens": (
                    int(os.environ["JOB_AI_MAX_OUTPUT_TOKENS"])
                    if os.environ.get("JOB_AI_MAX_OUTPUT_TOKENS")
                    else None
                ),
                "reasoning_effort": os.environ.get("JOB_AI_REASONING_EFFORT") or None,
            }
        )


def _optional_float(name: str) -> float | None:
    value = os.environ.get(name)
    return float(value) if value else None


class AiUsage(StrictModel):
    model_name: str
    calls: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class DailyJobsTarget(StrictModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    webhook_url: SecretStr | None = None
    bot_token: SecretStr | None = None
    channel_id: str | None = Field(default=None, pattern=r"^[0-9]{5,25}$")
    timezone: str = "America/New_York"

    @property
    def interactive(self) -> bool:
        return self.bot_token is not None


class AiModelOptions(StrictModel):
    provider: AiProvider | None = None
    model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    reasoning_effort: ReasoningEffort | None = None

    def apply(self, settings: AiSettings) -> AiSettings:
        changes = self.model_dump(exclude_unset=True)
        if self.provider is None:
            changes.pop("provider", None)
        if self.model is None:
            changes.pop("model", None)
        return AiSettings.model_validate({**settings.model_dump(), **changes})

    @classmethod
    def from_settings(cls, settings: AiSettings) -> "AiModelOptions":
        return cls.model_validate(settings.model_dump(include=set(cls.model_fields)))


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

DiscordLogLevel = Literal["WARNING", "ERROR", "CRITICAL"]


class LoggingSettings(StrictModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    level: LogLevel = "INFO"
    database_enabled: bool = False
    discord_webhook_url: SecretStr | None = None
    discord_level: DiscordLogLevel = "WARNING"
    discord_scrape_webhook_url: SecretStr | None = None
    discord_daily_jobs_webhook_url: SecretStr | None = None
    discord_daily_jobs_timezone: str = "America/New_York"
    discord_bot_token: SecretStr | None = None
    discord_daily_jobs_channel_id: str | None = Field(default=None, pattern=r"^[0-9]{5,25}$")

    @field_validator(
        "discord_webhook_url", "discord_scrape_webhook_url", "discord_daily_jobs_webhook_url"
    )
    @classmethod
    def validate_webhook(cls, value: SecretStr | None) -> SecretStr | None:
        if (
            value is not None
            and re.fullmatch(
                r"https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/(?:v\d+/)?"
                r"webhooks/\d+/[A-Za-z0-9._-]+",
                value.get_secret_value(),
            )
            is None
        ):
            raise ValueError("Use an HTTPS Discord webhook URL without query parameters")
        return value

    @field_validator("discord_bot_token")
    @classmethod
    def validate_bot_token(cls, value: SecretStr | None) -> SecretStr | None:
        if (
            value is not None
            and re.fullmatch(r"[A-Za-z0-9._-]{20,200}", value.get_secret_value()) is None
        ):
            raise ValueError("Use the bot token from the Discord Developer Portal's Bot page")
        return value

    @field_validator("discord_daily_jobs_timezone")
    @classmethod
    def validate_daily_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Use an IANA timezone for daily Discord reports") from error
        return value

    def daily_jobs_target(self) -> DailyJobsTarget | None:
        channel = self.discord_daily_jobs_channel_id
        if self.discord_daily_jobs_webhook_url is None and (
            self.discord_bot_token is None or channel is None
        ):
            return None
        return DailyJobsTarget(
            webhook_url=self.discord_daily_jobs_webhook_url,
            bot_token=self.discord_bot_token,
            channel_id=channel,
            timezone=self.discord_daily_jobs_timezone,
        )

    @classmethod
    def from_environment(cls) -> "LoggingSettings":
        load_environment()
        enabled = os.environ.get("JOB_LOG_DATABASE_ENABLED", "false").strip().lower()
        if enabled not in {"true", "false", "1", "0"}:
            raise ValueError("JOB_LOG_DATABASE_ENABLED must be true, false, 1, or 0")
        webhook = os.environ.get("JOB_DISCORD_WEBHOOK_URL", "").strip()
        scrape_webhook = os.environ.get("JOB_DISCORD_SCRAPE_WEBHOOK_URL", "").strip()
        daily_webhook = os.environ.get("JOB_DISCORD_DAILY_JOBS_WEBHOOK_URL", "").strip()
        bot_token = os.environ.get("JOB_DISCORD_BOT_TOKEN", "").strip()
        daily_channel = os.environ.get("JOB_DISCORD_DAILY_JOBS_CHANNEL_ID", "").strip()
        return cls.model_validate(
            {
                "level": os.environ.get("JOB_LOG_LEVEL", "INFO").strip().upper(),
                "database_enabled": enabled in {"true", "1"},
                "discord_webhook_url": SecretStr(webhook) if webhook else None,
                "discord_level": os.environ.get("JOB_DISCORD_LOG_LEVEL", "WARNING").strip().upper(),
                "discord_scrape_webhook_url": SecretStr(scrape_webhook) if scrape_webhook else None,
                "discord_daily_jobs_webhook_url": SecretStr(daily_webhook)
                if daily_webhook
                else None,
                "discord_daily_jobs_timezone": os.environ.get(
                    "JOB_DISCORD_DAILY_JOBS_TIMEZONE", "America/New_York"
                ).strip(),
                "discord_bot_token": SecretStr(bot_token) if bot_token else None,
                "discord_daily_jobs_channel_id": daily_channel or None,
            }
        )
