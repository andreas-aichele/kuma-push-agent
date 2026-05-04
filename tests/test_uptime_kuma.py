"""Tests for Uptime Kuma push client."""

from __future__ import annotations

import httpx
import pytest

from kuma_push_agent.uptime_kuma import _mask_url, push


def test_mask_url_replaces_token() -> None:
    url = "https://kuma.example.com/api/push/secrettoken123"
    masked = _mask_url(url)
    assert "secrettoken123" not in masked
    assert masked == "https://kuma.example.com/api/push/***"


def test_mask_url_no_path_unchanged() -> None:
    url = "https://kuma.example.com"
    assert _mask_url(url) == url


def test_mask_url_root_path_unchanged() -> None:
    url = "https://kuma.example.com/"
    assert _mask_url(url) == url


def test_mask_url_preserves_scheme_and_host() -> None:
    url = "https://monitoring.internal:8080/api/push/abc123"
    masked = _mask_url(url)
    assert masked.startswith("https://monitoring.internal:8080/api/push/")
    assert "abc123" not in masked
    assert "***" in masked


def test_push_success(mocker: pytest.MonkeyPatch) -> None:
    mock_get = mocker.patch("kuma_push_agent.uptime_kuma.httpx.get")
    mock_response = mocker.Mock()
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    push("https://kuma.example.com/api/push/token123", status="up", msg="OK", ping=42)

    assert mock_get.called
    call_url: str = mock_get.call_args[0][0]
    assert "status=up" in call_url
    assert "msg=OK" in call_url
    assert "ping=42" in call_url
    mock_response.raise_for_status.assert_called_once()


def test_push_url_encodes_special_chars(mocker: pytest.MonkeyPatch) -> None:
    mock_get = mocker.patch("kuma_push_agent.uptime_kuma.httpx.get")
    mock_response = mocker.Mock()
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    push(
        "https://kuma.example.com/api/push/tok",
        status="down",
        msg="MariaDB connection failed",
        ping=5000,
    )

    call_url: str = mock_get.call_args[0][0]
    assert "status=down" in call_url
    assert "ping=5000" in call_url
    assert "MariaDB+connection+failed" in call_url or "MariaDB%20connection%20failed" in call_url


def test_push_timeout_does_not_raise(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "kuma_push_agent.uptime_kuma.httpx.get",
        side_effect=httpx.TimeoutException("timed out"),
    )
    push("https://kuma.example.com/api/push/token123")  # must not raise


def test_push_http_status_error_does_not_raise(mocker: pytest.MonkeyPatch) -> None:
    mock_request = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.status_code = 500
    mocker.patch(
        "kuma_push_agent.uptime_kuma.httpx.get",
        side_effect=httpx.HTTPStatusError(
            "Internal Server Error",
            request=mock_request,
            response=mock_response,
        ),
    )
    push("https://kuma.example.com/api/push/token123")  # must not raise


def test_push_connect_error_does_not_raise(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "kuma_push_agent.uptime_kuma.httpx.get",
        side_effect=httpx.ConnectError("connection refused"),
    )
    push("https://kuma.example.com/api/push/token123")  # must not raise


def test_push_passes_timeout_to_httpx(mocker: pytest.MonkeyPatch) -> None:
    mock_get = mocker.patch("kuma_push_agent.uptime_kuma.httpx.get")
    mock_response = mocker.Mock()
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    push("https://kuma.example.com/api/push/tok")

    _, kwargs = mock_get.call_args
    assert kwargs.get("timeout") == 10.0
