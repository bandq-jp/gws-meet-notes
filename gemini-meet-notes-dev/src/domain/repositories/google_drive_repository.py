"""
Repository interface for Google Drive operations.
"""
from abc import ABC, abstractmethod
from typing import Optional
from ..entities.meet_recording import MeetRecording


class GoogleDriveRepository(ABC):
    """
    Repository interface for Google Drive operations.
    """
    
    @abstractmethod
    async def get_file_info(self, file_id: str, user_email: str) -> Optional[MeetRecording]:
        """Get file information from Google Drive."""
        pass
    
    @abstractmethod
    async def download_file_content(self, file_id: str, mime_type: str, user_email: str) -> str:
        """Download file content from Google Drive."""
        pass
    
    @abstractmethod
    async def setup_push_notifications(self, user_email: str, topic_path: str) -> dict:
        """Set up push notifications for Google Drive changes."""
        pass