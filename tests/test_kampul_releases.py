import asyncio
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

spec = spec_from_file_location('app.services.kampul_releases', Path(__file__).resolve().parents[1] / 'app/services/kampul_releases.py')
gateway = module_from_spec(spec)
spec.loader.exec_module(gateway)

def test_gateway_uses_only_kampul_and_server_school_identity(monkeypatch):
    monkeypatch.setattr(gateway.settings, 'kampul_release_api_url', 'https://sis.kampul.com')
    monkeypatch.setattr(gateway.settings, 'kampul_release_service_token', 'a' * 64)
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(url=SimpleNamespace(database='sis_my_school')))
    base, headers = gateway.release_connection(db)
    assert base == 'https://sis.kampul.com/api/desktop-releases'
    assert headers['X-Kampul-School'] == 'my-school'
    for bad in ('https://github.com', 'http://sis.kampul.com', 'https://sis.kampul.com.evil.test', 'https://sis.kampul.com/redirect'):
        monkeypatch.setattr(gateway.settings, 'kampul_release_api_url', bad)
        with pytest.raises(HTTPException): gateway.release_connection(db)

def test_outdated_and_missing_versions_cannot_access_desktop_data(monkeypatch):
    async def policy(_db): return {'minimumVersion': '2.3.0'}
    monkeypatch.setattr(gateway, 'catalog', policy)
    for version in ('', '2.2.9', 'invalid'):
        with pytest.raises(HTTPException) as error:
            asyncio.run(gateway.enforce_version(None, {'x-desktop-version':version}))
        assert error.value.status_code == 426
    asyncio.run(gateway.enforce_version(None, {'x-desktop-version':'2.3.0'}))
    asyncio.run(gateway.enforce_version(None, {'x-desktop-version':'2.10.0'}))

def test_gateway_does_not_accept_redirects_or_subscription_denial():
    for status in (301,302,401,403,404,500):
        with pytest.raises(HTTPException): gateway.check_response(SimpleNamespace(status_code=status))
    gateway.check_response(SimpleNamespace(status_code=200))
