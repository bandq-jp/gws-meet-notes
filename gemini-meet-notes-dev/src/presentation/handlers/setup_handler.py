"""
Cloud Run handler for infrastructure setup.
"""
import logging
from typing import Dict, Any
from ...application.services.application_service import MeetNotesApplicationService

logger = logging.getLogger(__name__)


class SetupHandler:
    """
    Handler for infrastructure setup endpoints.
    """
    
    def __init__(self, application_service: MeetNotesApplicationService):
        self.application_service = application_service
    
    async def handle_setup_request(
        self, 
        project_id: str, 
        topic_path: str
    ) -> Dict[str, Any]:
        """
        Handle infrastructure setup request.
        """
        try:
            logger.info(f"Setting up infrastructure for project: {project_id}")
            
            result = await self.application_service.setup_infrastructure(
                project_id, 
                topic_path
            )
            
            logger.info(f"Setup result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error during setup: {e}")
            return {
                "success": False,
                "error": f"Setup error: {str(e)}"
            }