"""
Pub/Sub related types and data structures.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class PubSubMessage:
    """Represents a Pub/Sub message."""
    data: bytes
    attributes: Dict[str, str]
    message_id: str
    publish_time: Optional[str] = None
    
    def get_attribute(self, key: str, default: str = "") -> str:
        """Get an attribute value with a default."""
        return self.attributes.get(key, default)


@dataclass
class DriveChangeNotification:
    """Represents a Google Drive change notification from Pub/Sub."""
    file_id: str
    change_type: str
    user_email: str
    
    @classmethod
    def from_pubsub_message(cls, message: PubSubMessage) -> 'DriveChangeNotification':
        """Create from a Pub/Sub message."""
        # Parse the message data (implementation depends on Google Drive notification format)
        import json
        try:
            data = json.loads(message.data.decode('utf-8'))
            return cls(
                file_id=data.get('fileId', ''),
                change_type=data.get('changeType', 'unknown'),
                user_email=message.get_attribute('userEmail', '')
            )
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Invalid Drive notification format: {e}")