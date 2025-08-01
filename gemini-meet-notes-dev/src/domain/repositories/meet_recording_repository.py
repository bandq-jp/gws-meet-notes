"""
Repository interface for meet recordings.
"""
from abc import ABC, abstractmethod
from typing import Optional
from ..entities.meet_recording import MeetRecording


class MeetRecordingRepository(ABC):
    """
    Repository interface for managing meet recordings.
    """
    
    @abstractmethod
    async def get_by_file_id(self, file_id: str) -> Optional[MeetRecording]:
        """Get a meet recording by file ID."""
        pass
    
    @abstractmethod
    async def save(self, recording: MeetRecording) -> None:
        """Save a meet recording."""
        pass
    
    @abstractmethod
    async def exists(self, file_id: str) -> bool:
        """Check if a recording with the given file ID exists."""
        pass