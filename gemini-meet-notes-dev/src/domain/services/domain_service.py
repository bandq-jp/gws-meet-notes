"""
Domain services for business logic that doesn't belong to a single entity.
"""
from ..entities.meet_recording import MeetRecording


class MeetRecordingDomainService:
    """
    Domain service for meet recording business logic.
    """
    
    @staticmethod
    def should_process_recording(recording: MeetRecording, target_user_email: str) -> bool:
        """
        Determine if a recording should be processed based on business rules.
        """
        # Business rule 1: Must be from Meet Recordings folder
        if not recording.is_from_meet_recordings_folder():
            return False
        
        # Business rule 2: Must be owned by target user
        if not recording.is_owned_by_target_user(target_user_email):
            return False
        
        # Business rule 3: Must not be already processed
        if recording.is_processed():
            return False
        
        # Business rule 4: Must be a Google Document
        if not recording.file_info.is_google_document():
            return False
        
        return True
    
    @staticmethod
    def generate_local_filename(recording: MeetRecording) -> str:
        """
        Generate a local filename for the recording.
        """
        # Sanitize filename
        safe_name = "".join(c for c in recording.file_info.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        timestamp = recording.created_at.strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{safe_name}.txt"