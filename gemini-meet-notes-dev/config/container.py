"""
Dependency injection container.
"""
from ..config.settings import ApplicationConfig, load_config
from ..infrastructure.google_apis.google_drive_client import GoogleDriveClient
from ..infrastructure.pubsub.pubsub_client import PubSubClient
from ..infrastructure.storage.local_storage_repository import LocalStorageMeetRecordingRepository
from ..application.use_cases.process_meet_recording_use_case import ProcessMeetRecordingUseCase
from ..application.use_cases.setup_infrastructure_use_case import SetupInfrastructureUseCase
from ..application.services.application_service import MeetNotesApplicationService
from ..presentation.handlers.pubsub_handler import PubSubHandler
from ..presentation.handlers.setup_handler import SetupHandler


class DIContainer:
    """
    Dependency injection container for the application.
    """
    
    def __init__(self):
        self._config = None
        self._instances = {}
    
    @property
    def config(self) -> ApplicationConfig:
        if self._config is None:
            self._config = load_config()
        return self._config
    
    def get_google_drive_client(self) -> GoogleDriveClient:
        if 'google_drive_client' not in self._instances:
            self._instances['google_drive_client'] = GoogleDriveClient(
                service_account_path=self.config.google_cloud.service_account_path,
                scopes=self.config.google_drive.scopes
            )
        return self._instances['google_drive_client']
    
    def get_pubsub_client(self) -> PubSubClient:
        if 'pubsub_client' not in self._instances:
            self._instances['pubsub_client'] = PubSubClient(
                project_id=self.config.google_cloud.project_id,
                service_account_path=self.config.google_cloud.service_account_path
            )
        return self._instances['pubsub_client']
    
    def get_meet_recording_repository(self) -> LocalStorageMeetRecordingRepository:
        if 'meet_recording_repo' not in self._instances:
            self._instances['meet_recording_repo'] = LocalStorageMeetRecordingRepository(
                storage_path=self.config.storage_path
            )
        return self._instances['meet_recording_repo']
    
    def get_process_recording_use_case(self) -> ProcessMeetRecordingUseCase:
        if 'process_recording_use_case' not in self._instances:
            self._instances['process_recording_use_case'] = ProcessMeetRecordingUseCase(
                google_drive_repo=self.get_google_drive_client(),
                meet_recording_repo=self.get_meet_recording_repository(),
                storage_path=self.config.storage_path
            )
        return self._instances['process_recording_use_case']
    
    def get_setup_infrastructure_use_case(self) -> SetupInfrastructureUseCase:
        if 'setup_infrastructure_use_case' not in self._instances:
            self._instances['setup_infrastructure_use_case'] = SetupInfrastructureUseCase(
                google_drive_repo=self.get_google_drive_client()
            )
        return self._instances['setup_infrastructure_use_case']
    
    def get_application_service(self) -> MeetNotesApplicationService:
        if 'application_service' not in self._instances:
            self._instances['application_service'] = MeetNotesApplicationService(
                process_recording_use_case=self.get_process_recording_use_case(),
                setup_infrastructure_use_case=self.get_setup_infrastructure_use_case(),
                target_user_email=self.config.target_user_email
            )
        return self._instances['application_service']
    
    def get_pubsub_handler(self) -> PubSubHandler:
        if 'pubsub_handler' not in self._instances:
            self._instances['pubsub_handler'] = PubSubHandler(
                application_service=self.get_application_service(),
                pubsub_client=self.get_pubsub_client()
            )
        return self._instances['pubsub_handler']
    
    def get_setup_handler(self) -> SetupHandler:
        if 'setup_handler' not in self._instances:
            self._instances['setup_handler'] = SetupHandler(
                application_service=self.get_application_service()
            )
        return self._instances['setup_handler']


# Global container instance
container = DIContainer()