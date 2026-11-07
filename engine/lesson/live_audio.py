"""Flux PCM borné et finals consommés pendant l'enregistrement."""

import asyncio


class LiveUtterance:
    def __init__(self, client, sample_rate, on_event, on_error, *, vocabulary=()):
        self.client, self.sample_rate = client, sample_rate
        self.on_event, self.on_error = on_event, on_error
        self.vocabulary = vocabulary
        self.queue = asyncio.Queue(256)
        self.sequence = 0
        self.size = 0
        self.stopped = False
        self.task = asyncio.create_task(self.run())

    def feed(self, sequence: int, data: bytes) -> None:
        if sequence < self.sequence:
            return
        if (self.stopped or self.task.done() or sequence != self.sequence or self.queue.full()
                or self.size + len(data) > 2 * 1024 * 1024 or len(data) % 2):
            raise ValueError("Flux PCM incomplet ou trop long")
        self.queue.put_nowait(data)
        self.sequence += 1
        self.size += len(data)

    def stop(self) -> None:
        if not self.stopped:
            self.stopped = True
            try:
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                self.task.cancel()
                raise ValueError("Flux audio saturé") from None

    async def read(self, session) -> None:
        async for event in session.events():
            if event.kind == "error":
                raise RuntimeError("Erreur du service de transcription")
            await self.on_event(event)

    async def run(self) -> None:
        session = None
        reader = None
        try:
            session = await asyncio.wait_for(self.client.open_live(
                   sample_rate=self.sample_rate, language="fr", endpointing_s=0.05,
                   vocabulary=self.vocabulary), 15)
            reader = asyncio.create_task(self.read(session))
            while True:
                chunk = await asyncio.wait_for(self.queue.get(), 60)
                if chunk is None:
                    break
                await asyncio.wait_for(session.send_audio(chunk), 5)
                if reader.done():
                    await reader
                    raise RuntimeError("Flux de transcription interrompu")
            await session.stop()
            await asyncio.wait_for(reader, 10)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.on_error()
        finally:
            if reader:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
            if session:
                await session.aclose()

    async def close(self) -> None:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
