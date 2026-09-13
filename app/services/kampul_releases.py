"""Private Kampul release gateway; never follows third-party download URLs."""
import re
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from ..core.config import settings


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.0)?', value or ''):
        raise HTTPException(426, 'A supported desktop version is required')
    return tuple(int(part) for part in value.split('.')[:3])


def release_connection(db):
    base = settings.kampul_release_api_url.rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme != 'https' or parsed.hostname != 'sis.kampul.com' or parsed.path not in ('', '/') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):
        raise HTTPException(503, 'Kampul release server is not configured correctly')
    token = settings.kampul_release_service_token
    if len(token) < 32:
        raise HTTPException(503, 'Kampul release service authentication is not configured')
    database = db.get_bind().url.database or ''
    slug = database[4:].replace('_', '-') if database.startswith('sis_') else settings.kampul_school_slug
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug or ''):
        raise HTTPException(403, 'A registered Kampul school is required')
    return base + '/api/desktop-releases', {'X-Kampul-Service-Token': token, 'X-Kampul-School': slug}


def check_response(response):
    if response.status_code in (401,403,404):
        raise HTTPException(response.status_code, 'Active paid subscription and an available release are required')
    if response.status_code != 200:
        raise HTTPException(503, 'Kampul release service is unavailable')


async def catalog(db):
    base, headers = release_connection(db)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(base, headers=headers)
            check_response(response)
            result = response.json()
            if not result.get('releases'):
                raise HTTPException(503, 'No Kampul desktop release has been published')
            version_tuple(result['minimumVersion'])
            for release in result['releases']:
                version_tuple(release['version'])
                if not re.fullmatch(r'[a-f0-9]{64}', release['sha256']):
                    raise ValueError('Invalid digest')
            return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Unable to verify Kampul release policy') from None


async def enforce_version(db, headers):
    policy = await catalog(db)
    if version_tuple(headers.get('x-desktop-version', '')) < version_tuple(policy['minimumVersion']):
        raise HTTPException(426, 'Update Kampul SIS to ' + policy['minimumVersion'] + ' or newer')
