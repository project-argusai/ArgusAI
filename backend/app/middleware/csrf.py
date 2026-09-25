"""Reject cross-origin state changes authenticated with browser cookies."""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.csrf import CSRF_EXEMPT_PATHS, cookie_write_origin_allowed

logger = logging.getLogger(__name__)


class CSRFMiddleware(BaseHTTPMiddleware):
    exempt_paths = CSRF_EXEMPT_PATHS

    def __init__(self, app, allowed_origins: list[str]):
        super().__init__(app)
        self.allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        if cookie_write_origin_allowed(
            method=request.method,
            cookie_names=set(request.cookies),
            headers=request.headers,
            allowed_origins=self.allowed_origins,
        ):
            return await call_next(request)

        logger.warning(
            "Cookie-authenticated state change rejected by Origin policy",
            extra={
                "event_type": "csrf_origin_denied",
                "path": request.url.path,
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Request origin is not allowed",
                "error_code": "CSRF_ORIGIN_DENIED",
            },
        )
