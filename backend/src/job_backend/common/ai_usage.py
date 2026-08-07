from threading import Lock

from job_backend.common.models import AiSettings, AiUsage


def completion_usage(
    settings: AiSettings, input_tokens: int | None = None, output_tokens: int | None = None
) -> AiUsage:
    return AiUsage(
        model_name=settings.model, calls=1, input_tokens=input_tokens, output_tokens=output_tokens
    )


class AiUsageTracker:
    def __init__(self, settings: AiSettings) -> None:
        self._lock = Lock()
        self._usage = completion_usage(settings, 0, 0).model_copy(update={"calls": 0})

    def record(self, usage: AiUsage) -> None:
        with self._lock:
            total = self._usage
            self._usage = total.model_copy(
                update={
                    "calls": total.calls + usage.calls,
                    "input_tokens": _add(total.input_tokens, usage.input_tokens),
                    "output_tokens": _add(total.output_tokens, usage.output_tokens),
                }
            )

    def snapshot(self) -> AiUsage:
        with self._lock:
            return self._usage.model_copy()


def _add(left: int | None, right: int | None) -> int | None:
    return left + right if left is not None and right is not None else None
