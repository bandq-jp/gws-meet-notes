"""
Use case for setting up the infrastructure (Google Drive push notifications).
"""
import logging
from dataclasses import dataclass
from typing import Dict, Any
from ...domain.repositories.google_drive_repository import GoogleDriveRepository
from ...shared.exceptions.infrastructure_exceptions import GoogleApiError

logger = logging.getLogger(__name__)


@dataclass
class SetupInfrastructureRequest:
    """Request DTO for infrastructure setup."""
    user_email: str
    topic_path: str
    project_id: str


@dataclass
class SetupInfrastructureResponse:
    """Response DTO for infrastructure setup."""
    success: bool
    channel_id: str = ""
    resource_id: str = ""
    expiration: str = ""
    error_message: str = ""


class SetupInfrastructureUseCase:
    """
    Use case for setting up Google Drive push notifications infrastructure.
    """
    
    def __init__(self, google_drive_repo: GoogleDriveRepository):
        self.google_drive_repo = google_drive_repo
    
    async def execute(self, request: SetupInfrastructureRequest) -> SetupInfrastructureResponse:
        """
        Execute the infrastructure setup.
        """
        try:
            logger.info(f"Setting up infrastructure for user: {request.user_email}")
            
            # Set up push notifications
            watch_response = await self.google_drive_repo.setup_push_notifications(
                request.user_email,
                request.topic_path
            )
            
            logger.info(f"Infrastructure setup completed for {request.user_email}")
            
            return SetupInfrastructureResponse(
                success=True,
                channel_id=watch_response.get('id', ''),
                resource_id=watch_response.get('resourceId', ''),
                expiration=watch_response.get('expiration', '')
            )
            
        except GoogleApiError as e:
            logger.error(f"Google API error during setup: {e}")
            return SetupInfrastructureResponse(
                success=False,
                error_message=f"Google API error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during setup: {e}")
            return SetupInfrastructureResponse(
                success=False,
                error_message=f"Unexpected error: {str(e)}"
            )