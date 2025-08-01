"""
Google Cloud Pub/Sub client implementation.
"""
import logging
from typing import Callable, Dict, Any
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from ...shared.exceptions.infrastructure_exceptions import PubSubError
from ...shared.types.pubsub_types import PubSubMessage, DriveChangeNotification

logger = logging.getLogger(__name__)


class PubSubClient:
    """
    Google Cloud Pub/Sub client for handling Drive change notifications.
    """
    
    def __init__(self, project_id: str, service_account_path: str):
        self.project_id = project_id
        
        # Load credentials
        try:
            credentials = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=['https://www.googleapis.com/auth/pubsub']
            )
            
            self.publisher = pubsub_v1.PublisherClient(credentials=credentials)
            self.subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
            
        except Exception as e:
            logger.error(f"Failed to initialize Pub/Sub client: {e}")
            raise PubSubError(f"Failed to initialize Pub/Sub client: {e}")
    
    def create_topic(self, topic_name: str) -> str:
        """Create a Pub/Sub topic."""
        try:
            topic_path = self.publisher.topic_path(self.project_id, topic_name)
            
            try:
                topic = self.publisher.create_topic(request={"name": topic_path})
                logger.info(f"Created topic: {topic.name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"Topic already exists: {topic_path}")
                else:
                    raise
            
            return topic_path
            
        except Exception as e:
            logger.error(f"Failed to create topic {topic_name}: {e}")
            raise PubSubError(f"Failed to create topic: {e}")
    
    def create_subscription(self, topic_name: str, subscription_name: str) -> str:
        """Create a Pub/Sub subscription."""
        try:
            topic_path = self.publisher.topic_path(self.project_id, topic_name)
            subscription_path = self.subscriber.subscription_path(
                self.project_id, subscription_name
            )
            
            try:
                subscription = self.subscriber.create_subscription(
                    request={
                        "name": subscription_path,
                        "topic": topic_path,
                    }
                )
                logger.info(f"Created subscription: {subscription.name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"Subscription already exists: {subscription_path}")
                else:
                    raise
            
            return subscription_path
            
        except Exception as e:
            logger.error(f"Failed to create subscription {subscription_name}: {e}")
            raise PubSubError(f"Failed to create subscription: {e}")
    
    def parse_drive_notification(self, pubsub_message: PubSubMessage) -> DriveChangeNotification:
        """Parse a Pub/Sub message into a Drive change notification."""
        try:
            return DriveChangeNotification.from_pubsub_message(pubsub_message)
        except Exception as e:
            logger.error(f"Failed to parse Drive notification: {e}")
            raise PubSubError(f"Failed to parse notification: {e}")
    
    def handle_pubsub_message(
        self, 
        message_data: Dict[str, Any], 
        handler: Callable[[DriveChangeNotification], Any]
    ) -> Any:
        """
        Handle a Pub/Sub message from Cloud Run.
        Expected format from Cloud Run Pub/Sub trigger:
        {
            "message": {
                "data": "base64-encoded-data",
                "attributes": {...},
                "messageId": "...",
                "publishTime": "..."
            }
        }
        """
        try:
            import base64
            
            message_info = message_data.get('message', {})
            
            # Decode base64 data
            data_b64 = message_info.get('data', '')
            data = base64.b64decode(data_b64) if data_b64 else b''
            
            # Create PubSubMessage
            pubsub_message = PubSubMessage(
                data=data,
                attributes=message_info.get('attributes', {}),
                message_id=message_info.get('messageId', ''),
                publish_time=message_info.get('publishTime')
            )
            
            # Parse into Drive notification
            notification = self.parse_drive_notification(pubsub_message)
            
            # Call handler
            return handler(notification)
            
        except Exception as e:
            logger.error(f"Failed to handle Pub/Sub message: {e}")
            raise PubSubError(f"Failed to handle message: {e}")