"""
Domain-specific exceptions.
"""


class DomainException(Exception):
    """Base exception for domain layer."""
    pass


class MeetRecordingNotFoundError(DomainException):
    """Raised when a meet recording is not found."""
    pass


class InvalidFileTypeError(DomainException):
    """Raised when trying to process an invalid file type."""
    pass


class UnauthorizedUserError(DomainException):
    """Raised when user is not authorized to access the resource."""
    pass


class FileAlreadyProcessedError(DomainException):
    """Raised when trying to process a file that has already been processed."""
    pass