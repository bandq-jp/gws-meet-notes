"""
File information value object.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FileInfo:
    """
    Value object representing file information from Google Drive.
    """
    file_id: str
    name: str
    mime_type: str
    folder_path: str
    size: Optional[int] = None
    
    def __post_init__(self):
        if not self.file_id:
            raise ValueError("File ID cannot be empty")
        if not self.name:
            raise ValueError("File name cannot be empty")
    
    def is_google_document(self) -> bool:
        """Check if the file is a Google Document."""
        return self.mime_type == "application/vnd.google-apps.document"
    
    def get_export_mime_type(self) -> str:
        """Get the appropriate MIME type for exporting."""
        if self.is_google_document():
            return "text/plain"
        return self.mime_type