MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ERROR_BYTES = 16 * 1024
MAX_CONSOLE_OUTPUT_CHARS = 32 * 1024
OUTPUT_INTERVAL_SECONDS = 1.0
REPORTED_INPUT = "[Saved in this report's input]"
REPORTED_SYSTEM_PROMPT = "[Saved in this report's system_prompt]"
REPORTED_OUTPUT = "[Saved in this report's output]"
CONNECT_ATTEMPTS = 6
CONNECT_RETRY_SECONDS = 2.0
REASONING_TIMEOUT_SECONDS = 300.0
SLOW_REASONING_EFFORTS = frozenset({"high", "xhigh", "max"})
ERROR_PARAMETERS = {
    "response_format": "structured output schema",
    "model": "configured model",
    "temperature": "configured temperature",
    "max_completion_tokens": "output token limit",
    "reasoning_effort": "reasoning effort",
}
