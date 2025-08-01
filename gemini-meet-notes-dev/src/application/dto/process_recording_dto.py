"""
Data Transfer Objects for processing recording use case.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProcessRecordingRequest:
    """Request DTO for processing a recording."""
    file_id: str
    user_email: str
    change_type: str = "created"


@dataclass
class ProcessRecordingResponse:
    """Response DTO for processing a recording."""
    success: bool
    file_id: str
    local_file_path: Optional[str] = None
    error_message: Optional[str] = None
    processed_content_length: Optional[int] = None