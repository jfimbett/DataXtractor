"""Custom exception hierarchy for DataXtractor."""

class DataXtractorError(Exception):
    """Base exception for application errors."""


class InvalidInputError(DataXtractorError):
    """Raised when the user supplies invalid input parameters."""


class DownloadError(DataXtractorError):
    """Raised when remote data could not be downloaded."""
