"""Authenticated third-party workflow broker for the always-online desktop app."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import PurePath
from typing import AsyncIterator
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...core import get_db, settings
from ...models import User
from .data import get_current_desktop_user


logger = logging.getLogger(__name__)
router = APIRouter()

_TELEGRAM_API_ROOT = "https://api.telegram.org"
_SAFE_PARSE_MODES = {"", "HTML", "Markdown", "MarkdownV2"}
_MAX_MESSAGE_LENGTH = 4096
_MAX_CAPTION_LENGTH = 1024


class TelegramMessageRequest(BaseModel):
    chat_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=_MAX_MESSAGE_LENGTH)
    parse_mode: str | None = Field(default=None, max_length=20)
    disable_web_page_preview: bool = True


class IntegrationResult(BaseModel):
    ok: bool = True


class ExchangeRateResponse(BaseModel):
    rate: int


class TimeResponse(BaseModel):
    utc_datetime: datetime


class TextValueResponse(BaseModel):
    value: str


class MapSearchResult(BaseModel):
    name: str = ""
    display_name: str
    lat: str
    lon: str


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(float(settings.desktop_external_timeout_seconds))


def _external_error(label: str, exc: Exception) -> HTTPException:
    logger.warning("Desktop %s integration failed: %s", label, exc)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{label} service is temporarily unavailable",
    )


def _telegram_token(db: Session) -> str:
    """Resolve the existing server-side token without returning it to desktop."""

    token = ""
    try:
        token_value = db.execute(
            text("SELECT telegrambot FROM settings WHERE telegrambot IS NOT NULL "
                 "AND TRIM(telegrambot) <> '' ORDER BY id LIMIT 1")
        ).scalar()
        token = str(token_value or "").strip()
    except SQLAlchemyError:
        db.rollback()
    if not token:
        try:
            token_value = db.execute(
                text("SELECT bot_token FROM telegram_attendance_settings "
                     "WHERE bot_token IS NOT NULL AND TRIM(bot_token) <> '' "
                     "ORDER BY id LIMIT 1")
            ).scalar()
            token = str(token_value or "").strip()
        except SQLAlchemyError:
            db.rollback()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telegram bot is not configured on the server",
        )
    return token


async def _telegram_post(
    db: Session,
    method: str,
    *,
    data: dict[str, str],
    files: dict | None = None,
) -> None:
    token = _telegram_token(db)
    url = f"{_TELEGRAM_API_ROOT}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.post(url, data=data, files=files)
        if response.is_success:
            payload = response.json()
            if bool(payload.get("ok")):
                return
        detail = "Telegram rejected the request"
        try:
            detail = str(response.json().get("description") or detail)
        except (TypeError, ValueError):
            pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise _external_error("Telegram", exc) from exc


@router.post("/telegram/message", response_model=IntegrationResult)
async def send_telegram_message(
    body: TelegramMessageRequest,
    current_user: User = Depends(get_current_desktop_user),
    db: Session = Depends(get_db),
) -> IntegrationResult:
    del current_user
    parse_mode = (body.parse_mode or "").strip()
    if parse_mode not in _SAFE_PARSE_MODES:
        raise HTTPException(status_code=400, detail="Unsupported Telegram parse mode")
    data = {"chat_id": body.chat_id.strip(), "text": body.text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    data["disable_web_page_preview"] = str(body.disable_web_page_preview).lower()
    await _telegram_post(db, "sendMessage", data=data)
    return IntegrationResult()


@router.post("/telegram/document", response_model=IntegrationResult)
async def send_telegram_document(
    chat_id: str = Form(..., min_length=1, max_length=100),
    caption: str = Form(default="", max_length=_MAX_CAPTION_LENGTH),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_desktop_user),
    db: Session = Depends(get_db),
) -> IntegrationResult:
    del current_user
    max_bytes = int(settings.desktop_resource_max_mb) * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Telegram document is too large")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="Only generated PDF documents are supported")
    filename = PurePath(file.filename or "document.pdf").name
    await _telegram_post(
        db,
        "sendDocument",
        data={"chat_id": chat_id.strip(), "caption": caption or ""},
        files={"document": (filename, content, "application/pdf")},
    )
    return IntegrationResult()


@router.post("/admission-form/{form_key}/consume")
async def consume_admission_form(
    form_key: str,
    current_user: User = Depends(get_current_desktop_user),
):
    del current_user
    try:
        safe_key = str(UUID(form_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid admission form key") from exc

    base_url = settings.desktop_admission_firebase_url.rstrip("/") + "/"
    url = f"{base_url}{safe_key}.json"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
            if payload is None:
                raise HTTPException(status_code=404, detail="Admission form is not ready")
            delete_response = await client.delete(url)
            delete_response.raise_for_status()
            return payload
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise _external_error("Admission form", exc) from exc


@router.get("/exchange-rate", response_model=ExchangeRateResponse)
async def get_exchange_rate(
    current_user: User = Depends(get_current_desktop_user),
) -> ExchangeRateResponse:
    del current_user
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.get(settings.desktop_exchange_rate_url)
            response.raise_for_status()
            ask = response.json()["data"]["ask"]
        rate = int(round(float(ask)))
        if rate <= 0:
            raise ValueError("exchange rate is not positive")
        return ExchangeRateResponse(rate=rate)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "Desktop exchange-rate provider unavailable; using legacy fallback 4100: %s",
            exc,
        )
        return ExchangeRateResponse(rate=4100)


@router.get("/time", response_model=TimeResponse)
def get_server_time(
    current_user: User = Depends(get_current_desktop_user),
) -> TimeResponse:
    del current_user
    return TimeResponse(utc_datetime=datetime.now(timezone.utc))


@router.get("/map/search", response_model=list[MapSearchResult])
async def search_map_locations(
    query: str,
    current_user: User = Depends(get_current_desktop_user),
) -> list[MapSearchResult]:
    del current_user
    normalized = query.strip()
    if not normalized or len(normalized) > 200:
        raise HTTPException(status_code=400, detail="Map search text is invalid")
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.get(
                settings.desktop_geocoding_url,
                params={"format": "jsonv2", "q": normalized, "limit": 5},
                headers={"User-Agent": "PAMAIS-School-Desktop-API/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        results: list[MapSearchResult] = []
        for item in payload[:5]:
            display_name = str(item.get("display_name") or "").strip()
            latitude = str(item.get("lat") or "").strip()
            longitude = str(item.get("lon") or "").strip()
            if not display_name or not latitude or not longitude:
                continue
            results.append(MapSearchResult(
                name=str(item.get("name") or "").strip(),
                display_name=display_name,
                lat=latitude,
                lon=longitude,
            ))
        return results
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise _external_error("Map search", exc) from exc


_VERSION_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 600.0  # 10 minutes cache
_FAST_FETCH_TIMEOUT_SECONDS = 5.0


async def _fetch_text(
    url: str,
    label: str,
    timeout_seconds: float | None = None,
    use_cache: bool = False,
) -> str:
    now = time.monotonic()
    if use_cache and url in _VERSION_CACHE:
        cached_content, expiry = _VERSION_CACHE[url]
        if now < expiry:
            return cached_content

    timeout = httpx.Timeout(timeout_seconds) if timeout_seconds else _timeout()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "PAMAIS-Desktop-API/1.0"})
            response.raise_for_status()
            text = response.text.strip("\ufeff \t\r\n")
            if use_cache:
                _VERSION_CACHE[url] = (text, now + _CACHE_TTL_SECONDS)
            return text
    except httpx.HTTPError as exc:
        if use_cache and url in _VERSION_CACHE:
            cached_content, _ = _VERSION_CACHE[url]
            logger.warning(
                "Desktop %s fetch failed (%s); serving stale cached response",
                label,
                exc,
            )
            return cached_content
        raise _external_error(label, exc) from exc


@router.get("/required-version", response_model=TextValueResponse)
async def get_required_version(current_user: User = Depends(get_current_desktop_user), db: Session = Depends(get_db)):
    from ...services.kampul_releases import catalog
    return TextValueResponse(value=(await catalog(db))["minimumVersion"])


@router.get("/update/releases")
async def available_releases(current_user: User = Depends(get_current_desktop_user), db: Session = Depends(get_db)):
    from ...services.kampul_releases import catalog
    return await catalog(db)


@router.get("/update/manifest", response_model=TextValueResponse)
async def get_update_manifest(current_user: User = Depends(get_current_desktop_user), db: Session = Depends(get_db)):
    from ...services.kampul_releases import catalog
    policy = await catalog(db)
    if not policy.get("releases"):
        return TextValueResponse(value="")
    release = policy["releases"][0]
    version = release['version']
    value = (f";aiu;\n[Update]\nProductVersion={version}\n"
             f"URL=https://sis.kampul.com/api/desktop-releases/{version}/download\n"
             f"ServerFileName=Kampul-SIS-{version}.exe\nSHA256={release['sha256']}\n"
             f"Size={release['size']}\nMinimumVersion={policy['minimumVersion']}\n"
             f"[Changelog]\n{release.get('notes', '')}")
    return TextValueResponse(value=value)


@router.get("/update/download")
async def download_update(version: str | None = None, current_user: User = Depends(get_current_desktop_user), db: Session = Depends(get_db)):
    from ...services.kampul_releases import catalog, release_connection, check_response, version_tuple
    policy = await catalog(db)
    version = version or policy['releases'][0]['version']
    version_tuple(version)
    release = next((r for r in policy['releases'] if r['version'] == version), None)
    if release is None:
        raise HTTPException(404, 'Release is no longer available')
    base, headers = release_connection(db)
    client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15), follow_redirects=False)
    try:
        response = await client.send(client.build_request('GET', f'{base}/{version}/download', headers=headers), stream=True)
        check_response(response)
    except Exception:
        await client.aclose()
        raise
    async def body():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()
    return StreamingResponse(body(), media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="Kampul-SIS-{version}.exe"',
        'Content-Length': str(release['size']), 'Cache-Control': 'private, no-store',
        'X-Checksum-SHA256': release['sha256'],
    })
