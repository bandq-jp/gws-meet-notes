"""
Local storage implementation for meet recording repository.
"""
import json
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from ...domain.repositories.meet_recording_repository import MeetRecordingRepository
from ...domain.entities.meet_recording import MeetRecording
from ...domain.value_objects.file_info import FileInfo
from ...domain.value_objects.user_info import UserInfo
from ...shared.exceptions.infrastructure_exceptions import FileStorageError

logger = logging.getLogger(__name__)


class LocalStorageMeetRecordingRepository(MeetRecordingRepository):
    """
    Local storage implementation of MeetRecordingRepository.
    Uses JSON files for simple persistence in Cloud Run environment.
    """
    
    def __init__(self, storage_path: str = "/tmp/recordings"):
        self.storage_path = storage_path
        self.metadata_file = os.path.join(storage_path, "recordings_metadata.json")
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self):
        """Ensure storage directory exists."""
        try:
            os.makedirs(self.storage_path, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create storage directory: {e}")
            raise FileStorageError(f"Failed to create storage directory: {e}")
    
    async def get_by_file_id(self, file_id: str) -> Optional[MeetRecording]:
        """Get a meet recording by file ID."""
        try:
            metadata = self._load_metadata()
            recording_data = metadata.get(file_id)
            
            if not recording_data:
                return None
            
            return self._deserialize_recording(recording_data)
            
        except Exception as e:
            logger.error(f"Failed to get recording by file_id {file_id}: {e}")
            raise FileStorageError(f"Failed to get recording: {e}")
    
    async def save(self, recording: MeetRecording) -> None:
        """Save a meet recording."""
        try:
            metadata = self._load_metadata()
            recording_data = self._serialize_recording(recording)
            metadata[recording.id] = recording_data
            
            self._save_metadata(metadata)
            logger.info(f"Saved recording: {recording.id}")
            
        except Exception as e:
            logger.error(f"Failed to save recording {recording.id}: {e}")
            raise FileStorageError(f"Failed to save recording: {e}")
    
    async def exists(self, file_id: str) -> bool:
        """Check if a recording with the given file ID exists."""
        try:
            metadata = self._load_metadata()
            return file_id in metadata
            
        except Exception as e:
            logger.error(f"Failed to check if recording exists {file_id}: {e}")
            raise FileStorageError(f"Failed to check existence: {e}")
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata from JSON file."""
        try:
            if not os.path.exists(self.metadata_file):
                return {}
            
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.warning(f"Failed to load metadata, starting with empty: {e}")
            return {}
    
    def _save_metadata(self, metadata: Dict[str, Any]) -> None:
        """Save metadata to JSON file."""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            raise FileStorageError(f"Failed to save metadata: {e}")
    
    def _serialize_recording(self, recording: MeetRecording) -> Dict[str, Any]:
        """Serialize a MeetRecording to dictionary."""
        return {
            'id': recording.id,
            'file_info': {
                'file_id': recording.file_info.file_id,
                'name': recording.file_info.name,
                'mime_type': recording.file_info.mime_type,
                'folder_path': recording.file_info.folder_path,
                'size': recording.file_info.size
            },
            'organizer': {
                'email': recording.organizer.email,
                'name': recording.organizer.name
            },
            'created_at': recording.created_at.isoformat(),
            'processed_at': recording.processed_at.isoformat() if recording.processed_at else None,
            'content': recording.content,
            'local_file_path': recording.local_file_path
        }
    
    def _deserialize_recording(self, data: Dict[str, Any]) -> MeetRecording:
        """Deserialize dictionary to MeetRecording."""
        file_info = FileInfo(
            file_id=data['file_info']['file_id'],
            name=data['file_info']['name'],
            mime_type=data['file_info']['mime_type'],
            folder_path=data['file_info']['folder_path'],
            size=data['file_info'].get('size')
        )
        
        organizer = UserInfo(
            email=data['organizer']['email'],
            name=data['organizer']['name']
        )
        
        created_at = datetime.fromisoformat(data['created_at'])
        processed_at = datetime.fromisoformat(data['processed_at']) if data['processed_at'] else None
        
        return MeetRecording(
            id=data['id'],
            file_info=file_info,
            organizer=organizer,
            created_at=created_at,
            processed_at=processed_at,
            content=data.get('content'),
            local_file_path=data.get('local_file_path')
        )