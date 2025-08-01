"""
Google Drive API client implementation.
"""
import uuid
import time
import logging
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ...domain.repositories.google_drive_repository import GoogleDriveRepository
from ...domain.entities.meet_recording import MeetRecording
from ...domain.value_objects.file_info import FileInfo
from ...domain.value_objects.user_info import UserInfo
from ...shared.exceptions.infrastructure_exceptions import GoogleApiError, AuthenticationError
from datetime import datetime

logger = logging.getLogger(__name__)


class GoogleDriveClient(GoogleDriveRepository):
    """
    Implementation of Google Drive repository using Google Drive API.
    """
    
    def __init__(self, service_account_path: str, scopes: list[str]):
        self.service_account_path = service_account_path
        self.scopes = scopes
        self._base_credentials = None
        self._load_base_credentials()
    
    def _load_base_credentials(self):
        """Load base service account credentials."""
        try:
            self._base_credentials = service_account.Credentials.from_service_account_file(
                self.service_account_path,
                scopes=self.scopes
            )
        except Exception as e:
            logger.error(f"Failed to load service account credentials: {e}")
            raise AuthenticationError(f"Failed to load credentials: {e}")
    
    def _get_delegated_service(self, user_email: str):
        """Get a Drive service with delegated credentials for the specified user."""
        try:
            delegated_credentials = self._base_credentials.with_subject(user_email)
            return build('drive', 'v3', credentials=delegated_credentials)
        except Exception as e:
            logger.error(f"Failed to create delegated service for {user_email}: {e}")
            raise AuthenticationError(f"Failed to create delegated service: {e}")
    
    async def get_file_info(self, file_id: str, user_email: str) -> Optional[MeetRecording]:
        """Get file information from Google Drive."""
        try:
            service = self._get_delegated_service(user_email)
            
            # Get file metadata
            file_metadata = service.files().get(
                fileId=file_id,
                fields='id,name,mimeType,parents,owners,createdTime'
            ).execute()
            
            # Get parent folder information to construct folder path
            folder_path = await self._get_folder_path(service, file_metadata.get('parents', []))
            
            # Extract owner information
            owners = file_metadata.get('owners', [])
            if not owners:
                logger.warning(f"No owners found for file {file_id}")
                return None
            
            owner = owners[0]  # Take the first owner
            user_info = UserInfo(
                email=owner.get('emailAddress', ''),
                name=owner.get('displayName', '')
            )
            
            # Create file info
            file_info = FileInfo(
                file_id=file_id,
                name=file_metadata['name'],
                mime_type=file_metadata['mimeType'],
                folder_path=folder_path
            )
            
            # Parse creation time
            created_at = datetime.fromisoformat(
                file_metadata['createdTime'].replace('Z', '+00:00')
            )
            
            return MeetRecording(
                id=file_id,
                file_info=file_info,
                organizer=user_info,
                created_at=created_at
            )
            
        except HttpError as e:
            logger.error(f"Google API error getting file info for {file_id}: {e}")
            if e.resp.status == 404:
                return None
            raise GoogleApiError(f"Failed to get file info: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting file info for {file_id}: {e}")
            raise GoogleApiError(f"Unexpected error: {e}")
    
    async def download_file_content(self, file_id: str, mime_type: str, user_email: str) -> str:
        """Download file content from Google Drive."""
        try:
            service = self._get_delegated_service(user_email)
            
            # Export Google Docs as plain text
            if mime_type == "text/plain":
                request = service.files().export_media(
                    fileId=file_id,
                    mimeType=mime_type
                )
            else:
                request = service.files().get_media(fileId=file_id)
            
            content = request.execute()
            
            if isinstance(content, bytes):
                return content.decode('utf-8')
            return str(content)
            
        except HttpError as e:
            logger.error(f"Google API error downloading file {file_id}: {e}")
            raise GoogleApiError(f"Failed to download file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error downloading file {file_id}: {e}")
            raise GoogleApiError(f"Unexpected error: {e}")
    
    async def setup_push_notifications(self, user_email: str, topic_path: str) -> dict:
        """Set up push notifications for Google Drive changes."""
        try:
            service = self._get_delegated_service(user_email)
            
            # Generate unique channel ID
            channel_id = str(uuid.uuid4())
            
            # Configure watch request
            watch_request = {
                'id': channel_id,
                'type': 'web_hook',
                'address': f'https://pubsub.googleapis.com/{topic_path}',
                'payload': True,
                'expiration': str(int((time.time() + 604800) * 1000))  # 7 days from now
            }
            
            # Set up watch on the entire Drive
            response = service.files().watch(
                fileId='root',
                body=watch_request
            ).execute()
            
            logger.info(f"Drive watch channel created for {user_email}: {response}")
            return response
            
        except HttpError as e:
            logger.error(f"Google API error setting up watch for {user_email}: {e}")
            raise GoogleApiError(f"Failed to setup watch: {e}")
        except Exception as e:
            logger.error(f"Unexpected error setting up watch for {user_email}: {e}")
            raise GoogleApiError(f"Unexpected error: {e}")
    
    async def _get_folder_path(self, service, parent_ids: list[str]) -> str:
        """Get the folder path for a file."""
        if not parent_ids:
            return "/"
        
        try:
            # Get parent folder info
            folder_info = service.files().get(
                fileId=parent_ids[0],
                fields='name,parents'
            ).execute()
            
            folder_name = folder_info.get('name', 'Unknown')
            
            # Recursively get parent path
            if 'parents' in folder_info:
                parent_path = await self._get_folder_path(service, folder_info['parents'])
                return f"{parent_path}/{folder_name}".replace('//', '/')
            else:
                return f"/{folder_name}"
                
        except Exception as e:
            logger.warning(f"Failed to get folder path: {e}")
            return "/Unknown"