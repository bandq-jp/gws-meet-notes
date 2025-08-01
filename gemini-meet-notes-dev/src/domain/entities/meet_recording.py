"""
Meeting recording entity - represents the core business object.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from ..value_objects.file_info import FileInfo
from ..value_objects.user_info import UserInfo


@dataclass
class MeetRecording:
    """
    Meeting recording entity representing a Google Meet recording document.
    """
    id: str
    file_info: FileInfo
    organizer: UserInfo
    created_at: datetime
    processed_at: Optional[datetime] = None
    content: Optional[str] = None
    local_file_path: Optional[str] = None
    
    def is_processed(self) -> bool:
        """Check if the recording has been processed."""
        return self.processed_at is not None
    
    def mark_as_processed(self, content: str, local_path: str) -> None:
        """Mark the recording as processed with content and local path."""
        self.processed_at = datetime.utcnow()
        self.content = content
        self.local_file_path = local_path
    
    def is_from_meet_recordings_folder(self) -> bool:
        """Check if the file is from Meet Recordings folder."""
        return "Meet Recordings" in self.file_info.folder_path
    
    def is_owned_by_target_user(self, target_email: str) -> bool:
        """Check if the recording is owned by the target user."""
        return self.organizer.email == target_email