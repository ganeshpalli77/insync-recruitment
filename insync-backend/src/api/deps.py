from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from src.config import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


ClientIP = Annotated[str, Depends(client_ip)]
