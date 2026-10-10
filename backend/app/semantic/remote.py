import asyncio
import time

from app.db.session import async_session_factory
from app.schemas.semantic_analysis import PassageExtraction
from app.semantic.ollama import PassageClientResult
from app.services.remote_ai import RemoteAiService


class RemoteSemanticClient:
    """A durable queue adapter; never connects from the VPS to the local PC."""
    def __init__(self, model, timeout_seconds):
        self.model, self.timeout_seconds = model, timeout_seconds

    async def analyze_passage(self, source_name, title, content):
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            async with async_session_factory() as session:
                task = await RemoteAiService(session).enqueue(self.model, source_name, title, content)
                await session.commit()
                if task.status == "success":
                    return PassageClientResult(PassageExtraction.model_validate(task.result),
                        task.prompt_tokens, task.completion_tokens)
                if task.status == "failed":
                    raise RuntimeError("Remote task exhausted its attempts; explicit retry required")
            if time.monotonic() >= deadline:
                # The job survives this scheduler cycle or a server restart. A
                # later cycle consumes its validated result without a new LLM call.
                raise TimeoutError("Local AI unavailable or busy; durable task retained")
            await asyncio.sleep(2)
