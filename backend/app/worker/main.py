"""Local-only Ollama runner. No database, Redis or browser credentials."""
import asyncio
from contextlib import suppress
import logging
import os
from urllib.parse import urlsplit

import httpx

from app.semantic.ollama import OllamaSemanticClient
from app.semantic.prompt import PROMPT_VERSION

logger = logging.getLogger("local-ai")


def api_url(value):
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("AI_SITE_URL must be an HTTPS origin without credentials or path")
    return value.rstrip("/") + "/api/v1/ai-worker"


async def deliver(api, task, body):
    # Retry only this result if the acknowledgement is lost; never redo inference.
    for attempt in range(6):
        try:
            response = await api.post(f"/{task['id']}/complete", json=body)
            if response.status_code == 409:
                logger.warning("Result rejected: lease expired or evidence invalid")
                return
            response.raise_for_status()
            return
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 5:
                raise
            await asyncio.sleep(min(30, 2 ** attempt))


async def execute_task(api, task, ollama_url, model):
    if task["model"] != model or task["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Incompatible worker task contract")
    timeout = task["timeout_seconds"]
    if not isinstance(timeout, int) or not 30 <= timeout <= 1800 or len(task["content"]) > 6000:
        raise ValueError("Invalid task budget")
    body = {"lease_id": task["lease_id"]}
    try:
        client = OllamaSemanticClient(ollama_url, model, timeout_seconds=timeout)
        result = await client.analyze_passage(task["source_name"], task["title"], task["content"])
        body.update(extraction=result.extraction.model_dump(mode="json"),
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens)
    except Exception:
        # No source text, token or provider response is logged or sent as an error.
        body["error_code"] = "ollama_failed"
        logger.warning("Ollama analysis failed; server will schedule a bounded retry")
    await deliver(api, task, body)


async def serve():
    site = api_url(os.environ.get("AI_SITE_URL", ""))
    token = os.environ.get("AI_WORKER_TOKEN", "")
    if len(token) < 32:
        raise ValueError("Configure a dedicated random AI_WORKER_TOKEN (at least 32 characters)")
    model = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
    async with httpx.AsyncClient(base_url=site, timeout=30, follow_redirects=False,
        headers={"Authorization": f"Bearer {token}"}, trust_env=False) as api:
        logger.info("Local AI worker started; outbound HTTPS polling only")
        pulse = asyncio.create_task(heartbeat(api, model))
        try:
            while True:
                try:
                    response = await api.post("/claim", json={"model": model, "prompt_version": PROMPT_VERSION})
                    response.raise_for_status()
                    task = response.json()["task"]
                    if task:
                        await execute_task(api, task, ollama_url, model)
                        logger.info("Task finished")
                        continue
                    await asyncio.sleep(10)
                except (httpx.HTTPError, ValueError, KeyError):
                    logger.warning("VPS unavailable or worker configuration rejected; retry in 30 seconds")
                    await asyncio.sleep(30)
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError):
                await pulse


async def heartbeat(api, model):
    while True:
        try:
            response = await api.post("/heartbeat", json={"model": model, "prompt_version": PROMPT_VERSION})
            response.raise_for_status()
        except httpx.HTTPError:
            pass
        await asyncio.sleep(30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # httpx logs full URLs; suppress them, including malformed server responses.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(serve())
