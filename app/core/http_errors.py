"""JSON-safe HTTP exception rendering.

Starlette's default HTTP exception handler passes ``detail`` directly to
``json.dumps``. Structured details containing values such as ``datetime`` can
therefore replace an intentional 4xx response with an unrelated 500. Encode
the payload through FastAPI's encoder first so the original status and detail
contract always reach clients.
"""

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response


async def json_safe_http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> Response:
    headers = exc.headers
    if exc.status_code < 200 or exc.status_code in {204, 205, 304}:
        return Response(status_code=exc.status_code, headers=headers)
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder({"detail": exc.detail}),
        headers=headers,
    )
