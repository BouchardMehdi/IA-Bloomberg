import hashlib
import re
from dataclasses import dataclass

PLAN_VERSION = "passages-v1"
DEFAULT_SIGNATURE = f"{PLAN_VERSION}:3000:3:9000"
SIGNALS = re.compile(
    r"\b(?:item\s+\d+\.\d+|acquir\w*|agreement|merger|revenue|earnings|dividend|"
    r"interest rates?|inflation|monetary|enforcement|approved|million|billion|"
    r"acquisition|accord|taux|résultat\w*)\b|[$€£]|\d+(?:\.\d+)?\s*%",
    re.I,
)
BOILERPLATE = re.compile(r"\b(?:forward-looking|safe harbor|signature|exhibit index)\b", re.I)


@dataclass(frozen=True)
class Passage:
    index: int
    start: int
    end: int
    text: str
    score: int

    @property
    def input_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


@dataclass(frozen=True)
class PassagePlan:
    chunks: tuple[Passage, ...]
    selected: tuple[Passage, ...]
    total_chars: int
    signature: str

    def coverage(self, statuses: dict[int, str], *, truncated: bool, source: str) -> dict:
        selected_ids = {p.index for p in self.selected}
        covered = sum(p.end - p.start for p in self.selected if statuses.get(p.index) == "success")
        return {
            "plan_version": PLAN_VERSION,
            "total_chars": self.total_chars,
            "chunk_count": len(self.chunks),
            "selected_count": len(self.selected),
            "analyzed_count": sum(statuses.get(p.index) == "success" for p in self.selected),
            "covered_chars": covered,
            "coverage_ratio": covered / self.total_chars if self.total_chars else 0,
            "document_truncated": truncated,
            "input_source": source,
            "passages": [
                {
                    "index": p.index,
                    "start": p.start,
                    "end": p.end,
                    "score": p.score,
                    "status": statuses.get(p.index, "pending")
                    if p.index in selected_ids
                    else "not_selected",
                }
                for p in self.chunks
            ],
        }


class PassagePlanner:
    def __init__(self, chunk_chars: int = 3000, max_passages: int = 3, budget_chars: int = 9000):
        if chunk_chars < 100 or max_passages < 1 or budget_chars < chunk_chars:
            raise ValueError("Invalid passage budget")
        self.chunk_chars = chunk_chars
        self.max_passages = max_passages
        self.budget_chars = budget_chars
        self.signature = f"{PLAN_VERSION}:{chunk_chars}:{max_passages}:{budget_chars}"

    def plan(self, text: str) -> PassagePlan:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_chars, len(text))
            if end < len(text):
                # Keep section headings or sentence boundaries where possible.
                tail_start = max(start + self.chunk_chars // 2, end - 700)
                matches = list(
                    re.finditer(
                        r"(?=\bItem\s+\d+\.\d+\b)|(?<=[.!?])\s+(?=[A-Z])|\n\n", text[tail_start:end]
                    )
                )
                if matches:
                    end = tail_start + matches[-1].start()
                else:
                    space = text.rfind(" ", tail_start, end)
                    if space > start:
                        end = space + 1
            value = text[start:end]
            score = len(SIGNALS.findall(value)) - 4 * len(BOILERPLATE.findall(value))
            chunks.append(Passage(len(chunks), start, end, value, score))
            start = end
        ranked = sorted(chunks, key=lambda p: (-p.score, p.index))
        # When no financial signal exists, sample across the text rather than only its start.
        if ranked and max(p.score for p in ranked) <= 0:
            count = min(len(chunks), self.max_passages)
            anchors = {i * (len(chunks) - 1) // max(1, count - 1) for i in range(count)}
            ranked = sorted(chunks, key=lambda p: (p.index not in anchors, p.index))
        selected = []
        remaining = self.budget_chars
        for passage in ranked:
            if len(selected) == self.max_passages:
                break
            if len(passage.text) <= remaining:
                selected.append(passage)
                remaining -= len(passage.text)
        return PassagePlan(
            tuple(chunks), tuple(sorted(selected, key=lambda p: p.index)), len(text), self.signature
        )
