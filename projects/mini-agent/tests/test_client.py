import httpx
import pytest

from mini_agent.client import is_retryable_error


def build_http_error(
    status_code: int,
) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST",
        "https://example.test/chat/completions",
    )
    response = httpx.Response(
        status_code,
        request=request,
    )

    return httpx.HTTPStatusError(
        "模拟 HTTP 错误",
        request=request,
        response=response,
    )


def test_transport_error_is_retryable():
    error = httpx.ConnectError("network down")

    assert is_retryable_error(error) is True


@pytest.mark.parametrize(
    "status_code",
    [429, 500, 502, 503, 504],
)
def test_retryable_http_status_codes(status_code):
    error = build_http_error(status_code)

    assert is_retryable_error(error) is True


@pytest.mark.parametrize(
    "status_code",
    [400, 401, 402, 403, 404],
)
def test_non_retryable_http_status_codes(
    status_code,
):
    error = build_http_error(status_code)

    assert is_retryable_error(error) is False