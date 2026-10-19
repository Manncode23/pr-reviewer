"""Fake LLM and realistic Gemini error messages for resilience tests."""

from app.schemas.findings import RawFinding, ReviewOutput, Severity

# Modeled on the real daily-quota error from your own run.
DAILY_429 = (
    "Error calling model 'gemini-3.8-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
    "{'error': {'code': 429, 'message': 'You exceeded your current quota, please check your "
    "plan and billing details. \n* Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, "
    "model: gemini-3.8-flash\nPlease retry in 8h49m34.212279678s.', "
    "'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': "
    "'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': "
    "'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
    "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
    "'quotaDimensions': {'model': 'gemini-3.8-flash', 'location': 'global'}, "
    "'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
    "'retryDelay': '31774s'}]}}"
)

PER_MINUTE_429 = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded for metric: "
    "generate_content_free_tier_requests, limit: 5, model: gemini-3.8-flash\n"
    "Please retry in 12.5s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': "
    "'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaId': "
    "'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}]}, "
    "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '12s'}]}}"
)

SERVER_503 = (
    "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is overloaded.', "
    "'status': 'UNAVAILABLE'}}"
)


def review_output(line: int = 2) -> ReviewOutput:
    return ReviewOutput(
        findings=[
            RawFinding(
                line=line, severity=Severity.HIGH, title="T", explanation="E",
                suggestion="S", confidence=0.9,
            )
        ]
    )


class FakeStructuredLLM:
    """Returns (or raises) the queued outputs, one per invoke() call."""

    def __init__(self, outputs: list) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        item = self.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeLLM:
    def __init__(self, structured: FakeStructuredLLM) -> None:
        self._structured = structured

    def with_structured_output(self, schema):
        return self._structured