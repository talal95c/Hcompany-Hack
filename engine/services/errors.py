"""Erreurs typées des services cloud : timeout, indisponibilité, quota et réponse invalide."""

from __future__ import annotations


class ServiceError(Exception):
    """Erreur d'un service cloud, toujours rattachée au service et à la requête."""

    kind = "error"

    def __init__(
        self, service: str, message: str, *, request_id: str | None = None, retry_after: float = 0
    ) -> None:
        super().__init__(f"{service}: {message}")
        self.service = service
        self.request_id = request_id
        self.retry_after = retry_after


class ServiceTimeout(ServiceError):
    kind = "timeout"


class ServiceUnavailable(ServiceError):
    kind = "unavailable"


class QuotaExceeded(ServiceError):
    kind = "quota"


class InvalidResponse(ServiceError):
    kind = "invalid_response"


class AuthenticationError(ServiceError):
    kind = "auth"


class InvalidRequest(ServiceError):
    kind = "invalid_request"


def error_for_status(
    service: str, status: int, body: str, *, request_id: str | None = None
) -> ServiceError:
    detail = body[:300]
    if status in (401, 403):
        return AuthenticationError(service, f"HTTP {status}", request_id=request_id)
    if status in (402, 429):
        return QuotaExceeded(service, f"HTTP {status} {detail}", request_id=request_id)
    if status in (408, 504):
        return ServiceTimeout(service, f"HTTP {status}", request_id=request_id)
    if status >= 500:
        return ServiceUnavailable(service, f"HTTP {status} {detail}", request_id=request_id)
    return InvalidRequest(service, f"HTTP {status} {detail}", request_id=request_id)
