"""Préparation STT sans audio et classification spéculative sans effet de bord."""

import asyncio
import time
import unicodedata


def normalize_utterance(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(" .!?…")


def _finished(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()


class PreopenedSession:
    def __init__(self, client, *, ttl_s: float = 20, interval_s: float = 5):
        self.client, self.ttl_s, self.interval_s = client, ttl_s, interval_s
        self.enabled = False
        self.spare = None
        self.config = None
        self.born = 0.
        self.active = 0
        self.pending = None
        self.rotation = None
        self.lock = asyncio.Lock()
        self.open_lock = asyncio.Lock()
        self.next_open = 0.

    def warm(self, **config) -> None:
        if not self.enabled or self.active or (self.pending and not self.pending.done()):
            return
        if (self.spare and self.config == config and time.monotonic() - self.born < self.ttl_s
                and not getattr(self.spare, "closed", False)):
            return
        self.pending = asyncio.create_task(self._prepare(config))
        self.pending.add_done_callback(_finished)

    async def _open(self, config):
        async with self.open_lock:
            await asyncio.sleep(max(0, self.next_open - time.monotonic()))
            self.next_open = time.monotonic() + self.interval_s
            try:
                return await asyncio.wait_for(self.client.open_live(**config), 15)
            except Exception as exc:
                self.next_open = max(self.next_open, time.monotonic()
                                     + max(30, getattr(exc, "retry_after", 0)))
                raise

    async def _prepare(self, config) -> None:
        session = None
        try:
            rotation, self.rotation = self.rotation, None
            if rotation:
                rotation.cancel()
                await asyncio.gather(rotation, return_exceptions=True)
            stale, self.spare = self.spare, None
            if stale:
                await stale.aclose()
            session = await self._open(config)
            if self.enabled and not self.active:
                self.spare, session = session, None
                self.config, self.born = config, time.monotonic()
                self.rotation = asyncio.create_task(self._rotate())
                self.rotation.add_done_callback(_finished)
        except Exception:
            pass
        finally:
            if session:
                await session.aclose()

    async def _rotate(self) -> None:
        await asyncio.sleep(self.ttl_s)
        async with self.lock:
            stale, self.spare = self.spare, None
            if stale:
                await stale.aclose()
            self.warm(**self.config)

    async def acquire(self, **config):
        async with self.lock:
            if self.pending and not self.pending.done():
                await asyncio.shield(self.pending)
            if not self.enabled:
                raise asyncio.CancelledError
            if self.rotation:
                self.rotation.cancel()
            session, self.spare = self.spare, None
            if session and (self.config != config or getattr(session, "closed", False)
                            or time.monotonic() - self.born >= self.ttl_s):
                await session.aclose()
                session = None
            if session is None:
                session = await self._open(config)
            if not self.enabled:
                await session.aclose()
                raise asyncio.CancelledError
            self.active += 1
            return session

    def release(self) -> None:
        self.active -= 1
        if self.config:
            self.warm(**self.config)

    async def close(self) -> None:
        self.enabled = False
        tasks = [t for t in (self.pending, self.rotation) if t and not t.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        spare, self.spare = self.spare, None
        if spare:
            await spare.aclose()


class IntentSpeculation:
    def __init__(self, classify, current, *, generation: int, stable_s: float = .2):
        self.classify, self.current = classify, current
        self.generation, self.stable_s = generation, stable_s
        self.text = ""
        self.task = None
        self.started = False
        self.tasks = set()

    def partial(self, text: str, *, immediate: bool = False) -> None:
        text = normalize_utterance(text)
        if text == self.text and self.task and (not immediate or self.started):
            return
        if self.task:
            self.task.cancel()
        self.text, self.started = text, False
        if not text or not self.current():
            return

        async def run():
            if not immediate:
                await asyncio.sleep(self.stable_s)
            if not self.current():
                return None
            self.started = True
            return await self.classify(text)

        self.task = asyncio.create_task(run())
        self.tasks.add(self.task)
        self.task.add_done_callback(self.tasks.discard)
        self.task.add_done_callback(_finished)

    def speech_end(self) -> None:
        self.partial(self.text, immediate=True)

    async def final(self, text: str):
        task = self.task
        if (task and self.started and self.current()
                and normalize_utterance(text) == self.text):
            try:
                result = await task
                if result is not None and self.current():
                    return self.text, self.generation, result
            except (Exception, asyncio.CancelledError):
                if asyncio.current_task().cancelling():
                    raise
        await self.close()
        return None

    async def close(self) -> None:
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.task, self.text = None, ""
