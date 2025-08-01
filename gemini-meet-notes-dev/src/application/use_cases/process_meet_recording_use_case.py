"""
Use case for processing Google Meet recordings.
"""
import os
import logging
from typing import Optional
from ..dto.process_recording_dto import ProcessRecordingRequest, ProcessRecordingResponse
from ...domain.repositories.google_drive_repository import GoogleDriveRepository
from ...domain.repositories.meet_recording_repository import MeetRecordingRepository
from ...domain.services.domain_service import MeetRecordingDomainService
from ...shared.exceptions.domain_exceptions import (
    MeetRecordingNotFoundError,
    InvalidFileTypeError,
    UnauthorizedUserError,
    FileAlreadyProcessedError
)

logger = logging.getLogger(__name__)


class ProcessMeetRecordingUseCase:
    """
    Use case for processing Google Meet recordings.
    Handles the complete workflow from receiving a file change notification
    to downloading and storing the recording content.
    """
    
    def __init__(
        self,
        google_drive_repo: GoogleDriveRepository,
        meet_recording_repo: MeetRecordingRepository,
        storage_path: str = "/tmp"
    ):
        self.google_drive_repo = google_drive_repo
        self.meet_recording_repo = meet_recording_repo
        self.storage_path = storage_path
        self.domain_service = MeetRecordingDomainService()
    
    async def execute(self, request: ProcessRecordingRequest) -> ProcessRecordingResponse:
        """
        Execute the use case to process a meet recording.
        """
        try:
            logger.info(f"Processing recording for file_id: {request.file_id}")
            
            # Step 1: Check if already processed
            if await self.meet_recording_repo.exists(request.file_id):
                logger.info(f"Recording {request.file_id} already processed")
                raise FileAlreadyProcessedError(f"Recording {request.file_id} already processed")
            
            # Step 2: Get file information from Google Drive
            recording = await self.google_drive_repo.get_file_info(
                request.file_id, 
                request.user_email
            )
            
            if not recording:
                logger.error(f"Recording not found: {request.file_id}")
                raise MeetRecordingNotFoundError(f"Recording not found: {request.file_id}")
            
            # Step 3: Apply business rules
            if not self.domain_service.should_process_recording(recording, request.user_email):
                logger.info(f"Recording {request.file_id} should not be processed")
                return ProcessRecordingResponse(
                    success=False,
                    file_id=request.file_id,
                    error_message="Recording does not meet processing criteria"
                )
            
            # Step 4: Download file content
            content = await self.google_drive_repo.download_file_content(
                request.file_id,
                recording.file_info.get_export_mime_type(),
                request.user_email
            )
            
            # Step 5: Save to local storage
            local_filename = self.domain_service.generate_local_filename(recording)
            local_file_path = os.path.join(self.storage_path, local_filename)
            
            await self._save_content_to_file(content, local_file_path)
            
            # Step 6: Mark as processed and save to repository
            recording.mark_as_processed(content, local_file_path)
            await self.meet_recording_repo.save(recording)
            
            logger.info(f"Successfully processed recording {request.file_id}")
            
            return ProcessRecordingResponse(
                success=True,
                file_id=request.file_id,
                local_file_path=local_file_path,
                processed_content_length=len(content)
            )
            
        except (MeetRecordingNotFoundError, InvalidFileTypeError, 
                UnauthorizedUserError, FileAlreadyProcessedError) as e:
            logger.warning(f"Domain error processing {request.file_id}: {e}")
            return ProcessRecordingResponse(
                success=False,
                file_id=request.file_id,
                error_message=str(e)
            )
        except Exception as e:
            logger.error(f"Unexpected error processing {request.file_id}: {e}")
            return ProcessRecordingResponse(
                success=False,
                file_id=request.file_id,
                error_message=f"Unexpected error: {str(e)}"
            )
    
    async def _save_content_to_file(self, content: str, file_path: str) -> None:
        """Save content to a local file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"Content saved to: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to save content to {file_path}: {e}")
            raise