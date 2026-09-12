# Expose the FastAPI app for FastAPI Cloud auto-discovery
# Lazy import to avoid RuntimeWarning when running via: python3 -m app.main
def __getattr__(name):
    if name == "app":
        from .main import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["app"]
