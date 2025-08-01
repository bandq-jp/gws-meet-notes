"""
Infrastructure-specific exceptions.
"""


class InfrastructureException(Exception):
    """Base exception for infrastructure layer."""
    pass


class GoogleApiError(InfrastructureException):
    """Raised when Google API calls fail."""
    pass


class PubSubError(InfrastructureException):
    """Raised when Pub/Sub operations fail."""
    pass


class FileStorageError(InfrastructureException):
    """Raised when file storage operations fail."""
    pass


class AuthenticationError(InfrastructureException):
    """Raised when authentication fails."""
    pass