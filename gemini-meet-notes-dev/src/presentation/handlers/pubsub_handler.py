"""
Cloud Run handler for Pub/Sub messages.
"""
import logging
import json
from typing import Dict, Any
from flask import Flask, request, jsonify
from ...application.services.application_service import MeetNotesApplicationService
from ...infrastructure.pubsub.pubsub_client import PubSubClient
from ...shared.exceptions.infrastructure_exceptions import PubSubError

logger = logging.getLogger(__name__)


class PubSubHandler:
    """
    Handler for Pub/Sub messages in Cloud Run environment.
    """
    
    def __init__(
        self,
        application_service: MeetNotesApplicationService,
        pubsub_client: PubSubClient
    ):
        self.application_service = application_service
        self.pubsub_client = pubsub_client
    
    async def handle_pubsub_message(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming Pub/Sub message from Cloud Run.
        """
        try:
            logger.info("Received Pub/Sub message")
            
            # Parse the Pub/Sub message and handle Drive notification
            result = self.pubsub_client.handle_pubsub_message(
                request_data,
                self.application_service.handle_drive_change_notification
            )
            
            logger.info(f"Processing result: {result}")
            return result
            
        except PubSubError as e:
            logger.error(f"Pub/Sub error: {e}")
            return {
                "success": False,
                "error": f"Pub/Sub error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error handling Pub/Sub message: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }