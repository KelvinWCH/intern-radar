from collections import deque
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import Future
from contextlib import AbstractContextManager, ExitStack
from queue import Queue
from threading import Thread
from types import TracebackType
from typing import Generic, TypeVar

Input = TypeVar("Input")
Output = TypeVar("Output")


class ResourcePool(Generic[Input, Output]):
    def __init__(
        self,
        factory: Callable[[], AbstractContextManager[Callable[[Input], Output]]],
        workers: int,
    ) -> None:
        if workers < 1:
            raise ValueError("At least one worker is required")
        self.factory = factory
        self.workers = workers
        self.queue: Queue[tuple[Input, Future[Output]] | None] = Queue(maxsize=workers * 2)
        self.threads: list[Thread] = []

    def __enter__(self) -> "ResourcePool[Input, Output]":
        self.threads = [Thread(target=self._run, name="scrape-reader") for _ in range(self.workers)]
        for thread in self.threads:
            thread.start()
        return self

    def _run(self) -> None:
        with ExitStack() as resources:
            reader: Callable[[Input], Output] | None = None
            while True:
                task = self.queue.get()
                if task is None:
                    return
                value, future = task
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    if reader is None:
                        reader = resources.enter_context(self.factory())
                    future.set_result(reader(value))
                except BaseException as error:
                    future.set_exception(error)

    def submit(self, value: Input) -> Future[Output]:
        future: Future[Output] = Future()
        self.queue.put((value, future))
        return future

    def map(self, values: Iterable[Input]) -> Generator[Output, None, None]:
        pending: deque[Future[Output]] = deque()
        try:
            for value in values:
                pending.append(self.submit(value))
                if len(pending) >= self.workers * 2:
                    yield pending.popleft().result()
            while pending:
                yield pending.popleft().result()
        finally:
            for future in pending:
                future.cancel()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for _ in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join()
