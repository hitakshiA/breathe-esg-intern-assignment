"""Tiny helper: write an AuditLog row from anywhere."""
from __future__ import annotations

from typing import Any

from .middleware import get_current_request
from .models import AuditLog


def record(
    organization,
    entity,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    req = get_current_request()
    user = getattr(req, "user", None) if req else None
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    AuditLog.objects.create(
        organization=organization,
        user=user,
        entity_type=type(entity).__name__,
        entity_id=str(getattr(entity, "id", "")),
        action=action,
        before=before or {},
        after=after or {},
        ip=_client_ip(req),
        user_agent=(req.META.get("HTTP_USER_AGENT", "")[:200] if req else ""),
    )


def _client_ip(req: Any) -> str | None:
    if req is None:
        return None
    fwd = req.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.META.get("REMOTE_ADDR")
