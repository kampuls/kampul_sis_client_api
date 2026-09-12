from datetime import datetime, timezone
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.http_errors import json_safe_http_exception_handler


class _Reason(str, Enum):
    primary_device = "primary_device"


def _client() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(
        StarletteHTTPException,
        json_safe_http_exception_handler,
    )

    @app.get("/structured-error")
    async def structured_error():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "attendance_primary_device_mismatch",
                "available_at": datetime(
                    2026,
                    8,
                    21,
                    6,
                    7,
                    32,
                    tzinfo=timezone.utc,
                ),
                "reason": _Reason.primary_device,
            },
            headers={"Retry-After": "60"},
        )

    return TestClient(app)


def test_structured_http_error_keeps_status_headers_and_json_safe_detail():
    response = _client().get("/structured-error")

    assert response.status_code == 409
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {
        "detail": {
            "code": "attendance_primary_device_mismatch",
            "available_at": "2026-08-21T06:07:32+00:00",
            "reason": "primary_device",
        }
    }
