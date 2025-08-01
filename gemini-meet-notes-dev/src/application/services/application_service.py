"""
Application services orchestrating multiple use cases.
"""
import logging
from typing import Dict, Any
from ..use_cases.process_meet_recording_use_case import (
    ProcessMeetRecordingUseCase,
    ProcessRecordingRequest
)
from ..use_cases.setup_infrastructure_use_case import (
    SetupInfrastructureUseCase,
    SetupInfrastructureRequest
)
from ...shared.types.pubsub_types import DriveChangeNotification

logger = logging.getLogger(__name__)


class MeetNotesApplicationService:
    """
    Application service coordinating meet notes processing.
    """
    
    def __init__(
        self,
        process_recording_use_case: ProcessMeetRecordingUseCase,
        setup_infrastructure_use_case: SetupInfrastructureUseCase,
        target_user_email: str
    ):
        self.process_recording_use_case = process_recording_use_case
        self.setup_infrastructure_use_case = setup_infrastructure_use_case
        self.target_user_email = target_user_email
    
    async def handle_drive_change_notification(
        self,
        notification: DriveChangeNotification
    ) -> Dict[str, Any]:
        """
        Handle a Google Drive change notification.
        """
        try:
            logger.info(f"Handling drive change notification: {notification}")
            
            # Only process changes for the target user
            if notification.user_email != self.target_user_email:
                logger.info(f"Ignoring notification for user: {notification.user_email}")
                return {"success": True, "message": "Ignored - not target user"}
            
            # Only process file creation events
            if notification.change_type not in ["created", "updated"]:
                logger.info(f"Ignoring change type: {notification.change_type}")
                return {"success": True, "message": f"Ignored - change type: {notification.change_type}"}
            
            # Process the recording
            request = ProcessRecordingRequest(
                file_id=notification.file_id,
                user_email=notification.user_email,
                change_type=notification.change_type
            )
            
            response = await self.process_recording_use_case.execute(request)
            
            return {
                "success": response.success,
                "file_id": response.file_id,
                "local_file_path": response.local_file_path,
                "error_message": response.error_message,
                "processed_content_length": response.processed_content_length
            }
            
        except Exception as e:
            logger.error(f"Error handling drive change notification: {e}")
            return {
                "success": False,
                "error_message": f"Error handling notification: {str(e)}"
            }
    
    async def setup_infrastructure(self, project_id: str, topic_path: str) -> Dict[str, Any]:
        """
        Set up the infrastructure for the target user.
        """
        try:
            request = SetupInfrastructureRequest(
                user_email=self.target_user_email,
                topic_path=topic_path,
                project_id=project_id
            )
            
            response = await self.setup_infrastructure_use_case.execute(request)
            
            return {
                "success": response.success,
                "channel_id": response.channel_id,
                "resource_id": response.resource_id,
                "expiration": response.expiration,
                "error_message": response.error_message
            }
            
        except Exception as e:
            logger.error(f"Error setting up infrastructure: {e}")
            return {
                "success": False,
                "error_message": f"Error setting up infrastructure: {str(e)}"
            }