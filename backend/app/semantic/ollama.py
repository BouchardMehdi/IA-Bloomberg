from dataclasses import dataclass

import httpx

from app.schemas.semantic_analysis import PassageExtraction, SemanticExtraction
from app.semantic.prompt import PASSAGE_SYSTEM_PROMPT, SYSTEM_PROMPT, build_user_prompt


@dataclass(frozen=True)
class SemanticClientResult:
    extraction: SemanticExtraction
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True)
class PassageClientResult:
    extraction: PassageExtraction
    prompt_tokens: int | None
    completion_tokens: int | None


class OllamaSemanticClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 600.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def analyze(
        self,
        source_name: str,
        title: str,
        content: str | None,
    ) -> SemanticClientResult:
        body = await self._chat(
            source_name, title, content, SYSTEM_PROMPT, SemanticExtraction.model_json_schema()
        )
        return SemanticClientResult(
            extraction=SemanticExtraction.model_validate_json(body["message"]["content"]),
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
        )

    async def analyze_passage(
        self, source_name: str, title: str, content: str
    ) -> PassageClientResult:
        body = await self._chat(
            source_name,
            title,
            content,
            PASSAGE_SYSTEM_PROMPT,
            PassageExtraction.model_json_schema(),
        )
        return PassageClientResult(
            extraction=PassageExtraction.model_validate_json(body["message"]["content"]),
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
        )

    async def _chat(
        self, source_name: str, title: str, content: str | None, system_prompt: str, schema: dict
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": build_user_prompt(source_name, title, content),
                },
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": 0, "num_predict": 1536},
        }
        if self._client is not None:
            response = await self._client.post("/api/chat", json=payload)
        else:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        return response.json()
