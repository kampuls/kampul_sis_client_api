from app.core.render_keepalive import resolve_render_keepalive_url


def test_uses_render_external_url_and_adds_health_path():
    assert (
        resolve_render_keepalive_url(
            "",
            "https://pamais-uptn.onrender.com",
        )
        == "https://pamais-uptn.onrender.com/health"
    )


def test_configured_render_health_url_takes_precedence():
    assert (
        resolve_render_keepalive_url(
            "https://pamais-uptn.onrender.com/health",
            "https://other.onrender.com",
        )
        == "https://pamais-uptn.onrender.com/health"
    )


def test_rejects_non_render_and_non_https_targets():
    assert (
        resolve_render_keepalive_url(
            "https://example.com/health",
            "",
        )
        is None
    )
    assert (
        resolve_render_keepalive_url(
            "http://pamais-uptn.onrender.com/health",
            "",
        )
        is None
    )
