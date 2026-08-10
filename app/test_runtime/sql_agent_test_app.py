from __future__ import annotations

from app.test_runtime.composition import create_shadow_test_asgi_app


def create_app():
    return create_shadow_test_asgi_app()
