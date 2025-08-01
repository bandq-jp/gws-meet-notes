"""
Application configuration settings.
"""
import os
from dataclasses import dataclass
from typing import List


@dataclass
class GoogleCloudConfig:
    """Google Cloud configuration."""
    project_id: str
    service_account_path: str
    pubsub_topic_name: str
    pubsub_subscription_name: str
    
    @property
    def topic_path(self) -> str:
        return f"projects/{self.project_id}/topics/{self.pubsub_topic_name}"
    
    @property
    def subscription_path(self) -> str:
        return f"projects/{self.project_id}/subscriptions/{self.pubsub_subscription_name}"


@dataclass
class GoogleDriveConfig:
    """Google Drive API configuration."""
    scopes: List[str]
    
    @classmethod
    def default(cls) -> 'GoogleDriveConfig':
        return cls(
            scopes=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/drive.metadata.readonly'
            ]
        )


@dataclass
class ApplicationConfig:
    """Main application configuration."""
    target_user_email: str
    storage_path: str
    log_level: str
    
    google_cloud: GoogleCloudConfig
    google_drive: GoogleDriveConfig


def load_config() -> ApplicationConfig:
    """Load configuration from environment variables."""
    
    # Required environment variables
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is required")
    
    target_user_email = os.getenv('TARGET_USER_EMAIL')
    if not target_user_email:
        raise ValueError("TARGET_USER_EMAIL environment variable is required")
    
    service_account_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '/app/service-account.json')
    
    # Optional environment variables with defaults
    pubsub_topic_name = os.getenv('PUBSUB_TOPIC_NAME', 'meet-notes-topic')
    pubsub_subscription_name = os.getenv('PUBSUB_SUBSCRIPTION_NAME', 'meet-notes-subscription')
    storage_path = os.getenv('STORAGE_PATH', '/tmp/recordings')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    return ApplicationConfig(
        target_user_email=target_user_email,
        storage_path=storage_path,
        log_level=log_level,
        google_cloud=GoogleCloudConfig(
            project_id=project_id,
            service_account_path=service_account_path,
            pubsub_topic_name=pubsub_topic_name,
            pubsub_subscription_name=pubsub_subscription_name
        ),
        google_drive=GoogleDriveConfig.default()
    )