"""Stash the current HTTP request on a thread-local for audit logging."""
from __future__ import annotations

import threading

_state = threading.local()


def get_current_request():
    return getattr(_state, "request", None)


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.request = request
        try:
            return self.get_response(request)
        finally:
            _state.request = None
