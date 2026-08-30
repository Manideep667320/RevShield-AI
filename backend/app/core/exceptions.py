"""
Custom exception hierarchy for the Revenue Recovery Engine.
All HTTP errors derive from AppError — handled globally in main.py.
"""
from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base application error with a default status code."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, detail: str):
        super().__init__(status_code=self.status_code, detail=detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class PolicyViolationError(AppError):
    status_code = status.HTTP_403_FORBIDDEN


class DuplicateError(AppError):
    status_code = status.HTTP_409_CONFLICT


class ExternalServiceError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY


class CircuitOpenError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class WorkflowError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class WebhookSignatureError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
