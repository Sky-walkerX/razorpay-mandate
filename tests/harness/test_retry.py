"""The 429 path. A rate limit killed a real run because nothing matched it."""
import pytest

from mandate.harness.agent_model import _is_retryable, _retry_delay


class _RateLimitError(Exception):
    pass


GEMINI_429 = (
    "Error code: 429 - {'error': {'message': 'You exceeded your current quota. "
    "Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 5, model: gemini-3.7-flash "
    "Please retry in 1.353865195s.', 'code': 'too_many_requests'}}"
)


@pytest.mark.parametrize("exc", [
    _RateLimitError(GEMINI_429),
    RuntimeError("Error code: 429 - too_many_requests"),
    RuntimeError("RESOURCE_EXHAUSTED: quota exceeded"),
    RuntimeError("503 Service Unavailable: model overloaded"),
    RuntimeError("Connection reset by peer"),
])
def test_transient_failures_are_retryable(exc):
    assert _is_retryable(exc) is True


@pytest.mark.parametrize("exc", [
    TypeError("unexpected keyword argument 'temperature'"),
    ValueError("bad schema"),
    RuntimeError("Error code: 400 - invalid_request"),
    RuntimeError("Error code: 401 - API key is invalid."),
])
def test_programming_and_auth_errors_are_not_retryable(exc):
    assert _is_retryable(exc) is False


def test_the_servers_suggested_delay_is_honoured():
    """Sleeping less than the server asked for just burns another attempt."""
    assert _retry_delay(_RateLimitError(GEMINI_429), attempt=0) == pytest.approx(
        1.353865195 + 0.5, abs=0.01)


def test_backoff_is_used_when_no_delay_is_suggested():
    assert _retry_delay(RuntimeError("429 too_many_requests"), attempt=0) == 2.0
    assert _retry_delay(RuntimeError("429 too_many_requests"), attempt=2) == 8.0
