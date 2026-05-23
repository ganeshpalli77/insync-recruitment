from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from src.config import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]


def client_ip(request: Request) -> str:
    from src.services.limiter import real_client_ip

    return real_client_ip(request)


ClientIP = Annotated[str, Depends(client_ip)]
