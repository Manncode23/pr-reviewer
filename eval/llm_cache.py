"""Record-and-replay cache for LLM calls, used by the evaluation harness.

Why: the free Gemini tier allows ~20 requests per day, and an eval run needs
more. Every response is stored on disk, keyed by a hash of (model, schema,
prompt), so re-runs are free, an interrupted run resumes where it stopped,
and changing a prompt re-queries only the prompts that actually changed.
"""

import hashlib
import json
import threading
from pathlib import Path


class EvalBudgetExhausted(Exception):
    """The per-run limit on live LLM calls was reached."""


class _CachingStructured:
    def __init__(self, parent: "CachingLLM", real, schema) -> None:
        self._parent = parent
        self._real = real
        self._schema = schema

    def invoke(self, messages):
        key = self._parent.key_for(self._schema, messages)
        path = self._parent.path_for(key)

        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._parent.record_hit()
            return self._schema.model_validate(data["output"])

        self._parent.reserve_live_call()
        output = self._real.invoke(messages)
        if output is None:
            return None  # nothing worth caching

        record = {
            "model": self._parent.model_name,
            "schema": self._schema.__name__,
            "output": output.model_dump(mode="json"),
        }
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return output


class CachingLLM:
    """Wraps an LLM so structured calls are served from disk when possible."""

    def __init__(self, real_llm, cache_dir: Path, model_name: str, max_live_calls: int) -> None:
        self._real = real_llm
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self._max_live_calls = max_live_calls
        self._lock = threading.Lock()
        self.live_calls = 0
        self.cache_hits = 0

    def with_structured_output(self, schema):
        return _CachingStructured(self, self._real.with_structured_output(schema), schema)

    def key_for(self, schema, messages) -> str:
        payload = json.dumps(
            {
                "model": self.model_name,
                "schema": schema.__name__,
                "messages": [[m.type, m.content] for m in messages],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        return self._dir / f"{key[:40]}.json"

    def record_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def reserve_live_call(self) -> None:
        with self._lock:
            if self.live_calls >= self._max_live_calls:
                raise EvalBudgetExhausted("live LLM call budget reached for this run")
            self.live_calls += 1