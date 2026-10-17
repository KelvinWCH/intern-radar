import json
import random
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from threading import Event
from typing import Protocol

from pydantic import JsonValue, SecretStr, TypeAdapter
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from job_backend.common.logger import get_logger

logger = get_logger(__name__)
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
_EVENT = TypeAdapter(dict[str, JsonValue])
_FATAL_CLOSE_CODES = {4004, 4010, 4011, 4012, 4013, 4014}
_QUIET_FAILURES = 5


class Socket(Protocol):
    def recv(self, timeout: float | None = None) -> str | bytes: ...

    def send(self, message: str) -> None: ...


OpenSocket = Callable[[str], AbstractContextManager[Socket]]


def _open_socket(url: str) -> AbstractContextManager[Socket]:
    return connect(url, open_timeout=20, close_timeout=5, max_size=4 * 2**20)


class GatewayStopped(Exception):
    pass


class DiscordGateway:
    def __init__(
        self,
        token: SecretStr,
        on_interaction: Callable[[dict[str, JsonValue]], None],
        *,
        open_socket: OpenSocket = _open_socket,
        url: str = GATEWAY_URL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._on_interaction = on_interaction
        self._open_socket = open_socket
        self._url = url
        self._clock = clock

    def run(self, stop: Event) -> None:
        failures = 0
        while not stop.is_set():
            try:
                self._session(stop)
                failures = 0
            except GatewayStopped as error:
                logger.error("Discord bot stopped: %s", error)
                return
            except Exception as error:
                failures += 1
                log = logger.warning if failures == _QUIET_FAILURES else logger.info
                log(
                    "Discord gateway disconnected (%s, %d in a row); reconnecting",
                    type(error).__name__,
                    failures,
                )
            # discord wants a 1-5s pause before identifying again
            delay = (
                min(300.0, 2.0 ** min(failures, 9)) * (0.5 + random.random() / 2)
                if failures
                else 1 + 4 * random.random()
            )
            if stop.wait(delay):
                return

    def _session(self, stop: Event) -> None:
        with self._open_socket(self._url) as socket:
            hello = self._receive(socket, 30)
            data = hello.get("d")
            if hello.get("op") != 10 or not isinstance(data, dict):
                raise ValueError("Discord gateway did not start with Hello")
            interval_ms = data.get("heartbeat_interval")
            if not isinstance(interval_ms, int | float) or not 1000 <= interval_ms <= 600_000:
                raise ValueError("Discord gateway sent an invalid heartbeat interval")
            interval = interval_ms / 1000
            socket.send(
                json.dumps(
                    {
                        "op": 2,
                        "d": {
                            "token": self._token.get_secret_value(),
                            "intents": 0,
                            "properties": {
                                "os": "linux",
                                "browser": "intern-radar",
                                "device": "intern-radar",
                            },
                        },
                    }
                )
            )
            sequence: int | None = None
            acknowledged = True
            beat_at = self._clock() + interval * random.random()
            while not stop.is_set():
                if self._clock() >= beat_at:
                    if not acknowledged:
                        raise TimeoutError("Discord did not acknowledge the last heartbeat")
                    socket.send(json.dumps({"op": 1, "d": sequence}))
                    acknowledged = False
                    beat_at = self._clock() + interval
                try:
                    event = self._receive(socket, min(1.0, max(0.0, beat_at - self._clock())))
                except TimeoutError:
                    continue
                operation = event.get("op")
                number = event.get("s")
                if isinstance(number, int):
                    sequence = number
                if operation == 0:
                    self._dispatch(event)
                elif operation == 1:
                    beat_at = self._clock()
                elif operation == 11:
                    acknowledged = True
                elif operation in {7, 9}:
                    logger.info("Discord asked the bot to reconnect (op %s)", operation)
                    return

    def _dispatch(self, event: dict[str, JsonValue]) -> None:
        kind = event.get("t")
        data = event.get("d")
        if kind == "READY" and isinstance(data, dict):
            user = data.get("user")
            name = user.get("username") if isinstance(user, dict) else None
            logger.info("Discord bot connected as %s", name if isinstance(name, str) else "?")
        elif kind == "INTERACTION_CREATE" and isinstance(data, dict):
            self._on_interaction(data)

    @staticmethod
    def _receive(socket: Socket, timeout: float) -> dict[str, JsonValue]:
        try:
            return _EVENT.validate_json(socket.recv(timeout=timeout))
        except ConnectionClosed as error:
            if error.rcvd is not None and error.rcvd.code in _FATAL_CLOSE_CODES:
                raise GatewayStopped(
                    f"Discord closed the gateway with code {error.rcvd.code}; "
                    "check JOB_DISCORD_BOT_TOKEN"
                ) from error
            raise
