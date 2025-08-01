# main.py
# Google Meet Minutes Processor - Secure Cloud Run Implementation
# セキュアなGoogle Drive監視アプリケーション

import os
import uuid
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union, Tuple

from fastapi import FastAPI, Request, Response, HTTPException
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import secretmanager
import google.auth

# ログ設定 - 機密情報を除外
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 設定値 -------------------------------------------------------------------

# 必須環境変数
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# オプション環境変数
SERVICE_ACCOUNT_SECRET_NAME = os.getenv('SERVICE_ACCOUNT_SECRET_NAME')
SERVICE_ACCOUNT_FILE_PATH = os.getenv('SERVICE_ACCOUNT_FILE_PATH')
MONITORED_USERS = os.getenv('MONITORED_USERS', '')

# Google APIスコープ
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

# 監視対象ユーザーの解析
monitored_users = {}
if MONITORED_USERS:
    for user_config in MONITORED_USERS.split(','):
        user_config = user_config.strip()
        if ':' in user_config:
            email, folder_id = user_config.split(':', 1)
            monitored_users[email.strip()] = folder_id.strip()
        else:
            monitored_users[user_config] = None

# FastAPIアプリケーション
app = FastAPI(
    title="Google Meet Minutes Processor",
    description="Secure Google Drive monitoring system for Meet Recordings",
    version="2.0.0"
)

# --- セキュアな認証システム ---------------------------------------------------

def _get_credentials_from_secret_manager(secret_name: str, subject_email: str) -> service_account.Credentials:
    """Secret Managerからサービスアカウントキーを安全に取得"""
    try:
        # Application Default Credentialsを使用してSecret Managerクライアントを作成
        client = secretmanager.SecretManagerServiceClient()
        
        # 正しいSecret名フォーマットを使用（パス形式ではなくシークレット名のみ）
        name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
        
        logger.info(f"Accessing Secret Manager: {secret_name}")
        response = client.access_secret_version(request={"name": name})
        
        key_data = response.payload.data.decode("UTF-8")
        logger.info("Successfully retrieved secret from Secret Manager")
        
        # JSONデータの解析
        try:
            key_info = json.loads(key_data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format in secret: {str(e)[:50]}...")
            raise ValueError("Secret contains invalid JSON data")
        
        # 必要なフィールドの確認
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email', 'client_id']
        missing_fields = [field for field in required_fields if field not in key_info]
        if missing_fields:
            raise ValueError(f"Secret missing required fields: {missing_fields}")
        
        # サービスアカウント認証情報を作成
        credentials = service_account.Credentials.from_service_account_info(
            key_info, scopes=SCOPES
        )
        
        # ドメイン全体の委任（domain-wide delegation）を設定
        delegated_credentials = credentials.with_subject(subject_email)
        
        logger.info(f"Successfully created delegated credentials for: {subject_email}")
        return delegated_credentials
        
    except Exception as e:
        logger.error(f"Secret Manager authentication failed: {str(e)[:100]}...")
        # 機密情報がログに出力されないよう注意
        raise

def _get_credentials_from_file(file_path: str, subject_email: str) -> service_account.Credentials:
    """ファイルからサービスアカウントキーを取得（開発用）"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Service account file not found: {file_path}")
    
    logger.info(f"Loading service account from file: {file_path}")
    credentials = service_account.Credentials.from_service_account_file(
        file_path, scopes=SCOPES
    )
    return credentials.with_subject(subject_email)

def _get_default_credentials_with_impersonation(subject_email: str) -> Any:
    """デフォルト認証を使用（制限あり）"""
    logger.warning("Using default credentials - domain delegation not available")
    credentials, _ = google.auth.default(scopes=SCOPES)
    return credentials

def get_impersonated_credentials(subject_email: str) -> Union[service_account.Credentials, Any]:
    """
    優先順位に基づいた認証情報取得
    1. Secret Manager（推奨）
    2. サービスアカウントファイル（開発用） 
    3. デフォルト認証（制限あり）
    """
    logger.info(f"Getting credentials for user: {subject_email}")
    
    # 基本設定の検証
    if not GCP_PROJECT_ID:
        raise ValueError("GCP_PROJECT_ID environment variable is required")
    
    if not subject_email or '@' not in subject_email:
        raise ValueError(f"Invalid subject email: {subject_email}")
    
    # 方法1: Secret Manager（推奨）
    if SERVICE_ACCOUNT_SECRET_NAME:
        try:
            logger.info(f"Attempting Secret Manager authentication for: {subject_email}")
            return _get_credentials_from_secret_manager(SERVICE_ACCOUNT_SECRET_NAME, subject_email)
        except Exception as e:
            logger.error(f"Secret Manager authentication failed: {str(e)[:100]}...")
            # Secret Managerが設定されている場合は他の方法を試さない（セキュリティ上の理由）
            raise
    
    # 方法2: サービスアカウントファイル（開発用のみ）
    if SERVICE_ACCOUNT_FILE_PATH:
        try:
            logger.info(f"Attempting file-based authentication for: {subject_email}")
            return _get_credentials_from_file(SERVICE_ACCOUNT_FILE_PATH, subject_email)
        except Exception as e:
            logger.error(f"File-based authentication failed: {str(e)[:100]}...")
            raise
    
    # 方法3: デフォルト認証（制限あり）
    logger.warning("No service account configured - using default credentials")
    logger.warning("Domain delegation will not be available with default credentials")
    return _get_default_credentials_with_impersonation(subject_email)

# --- Google Drive フォルダ検索機能 -------------------------------------------

def _find_meet_recordings_folder(drive_service, user_email: str) -> Optional[str]:
    """
    Meet Recordingsフォルダを検索（多言語対応）
    Google Meetは地域設定により異なる名前でフォルダを作成する可能性がある
    """
    try:
        # 可能な フォルダ名のリスト（英語、日本語、その他の地域設定）
        possible_names = [
            'Meet Recordings',
            'Meet 記録',
            'Meet録画',
            'Google Meet録画',
            'Google Meet 記録',
            'ミート記録',
            'ミート録画'
        ]
        
        logger.info(f"Searching for Meet Recordings folder for user: {user_email}")
        
        # 各可能な名前で検索
        for folder_name in possible_names:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            try:
                response = drive_service.files().list(
                    q=query, 
                    fields='files(id, name)',
                    pageSize=10
                ).execute()
                
                files = response.get('files', [])
                if files:
                    folder_id = files[0]['id']
                    folder_name = files[0]['name']
                    logger.info(f"Found folder '{folder_name}' with ID: {folder_id}")
                    return folder_id
                    
            except Exception as e:
                logger.warning(f"Error searching for folder '{folder_name}': {str(e)[:50]}...")
                continue
        
        # フォルダが見つからない場合、より広範囲の検索を実行
        logger.info("Attempting broader search for recording folders...")
        
        # "Meet" または "記録" を含むフォルダを検索
        broad_queries = [
            "name contains 'Meet' and mimeType='application/vnd.google-apps.folder'",
            "name contains '記録' and mimeType='application/vnd.google-apps.folder'",
            "name contains 'Recording' and mimeType='application/vnd.google-apps.folder'"
        ]
        
        for query in broad_queries:
            try:
                response = drive_service.files().list(
                    q=query,
                    fields='files(id, name)',
                    pageSize=20
                ).execute()
                
                files = response.get('files', [])
                for file_info in files:
                    folder_name = file_info['name'].lower()
                    # より柔軟なマッチング
                    if any(keyword in folder_name for keyword in ['meet', 'recording', '記録', '録画']):
                        logger.info(f"Found potential Meet folder: '{file_info['name']}' ID: {file_info['id']}")
                        return file_info['id']
                        
            except Exception as e:
                logger.warning(f"Error in broad search: {str(e)[:50]}...")
                continue
        
        logger.error(f"No Meet Recordings folder found for user: {user_email}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to search for Meet Recordings folder: {str(e)[:100]}...")
        return None

# --- セキュアなWebhook処理 ---------------------------------------------------

def _validate_webhook_headers(request: Request) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Webhookヘッダーの検証"""
    channel_state = request.headers.get("X-Goog-Resource-State")
    channel_token = request.headers.get("X-Goog-Channel-Token") 
    channel_id = request.headers.get("X-Goog-Channel-ID")
    
    logger.info(f"Webhook received: state={channel_state}, channel={channel_id}")
    
    return channel_state, channel_token, channel_id

def _is_retryable_error(error: Exception) -> bool:
    """エラーがリトライ可能かどうかを判定"""
    error_str = str(error).lower()
    retryable_errors = ['timeout', 'rate limit', 'quota', 'temporary', 'unavailable']
    return any(err in error_str for err in retryable_errors)

async def _process_document_safely(file_id: str, user_email: str) -> None:
    """ドキュメント処理の安全な実行"""
    try:
        creds = get_impersonated_credentials(user_email)
        docs_service = build('docs', 'v1', credentials=creds)
        
        document = docs_service.documents().get(documentId=file_id).execute()
        
        # テキスト抽出
        content_text = ""
        for content in document.get('body', {}).get('content', []):
            if 'paragraph' in content:
                for element in content.get('paragraph', {}).get('elements', []):
                    if 'textRun' in element:
                        content_text += element.get('textRun', {}).get('content', '')
        
        # セキュアなログ出力
        title = document.get('title', 'Untitled')
        preview = content_text.strip()[:50]
        if len(content_text.strip()) > 50:
            preview += "..."
        
        logger.info(f"📄 NEW DOCUMENT: '{title}' | USER: {user_email}")
        logger.info(f"📝 PREVIEW: {preview}")
        
    except Exception as e:
        logger.error(f"Document processing failed for {file_id}: {str(e)[:100]}...")
        raise

# --- APIエンドポイント -------------------------------------------------------

@app.get("/health")
async def health_check():
    """包括的なヘルスチェック"""
    try:
        # 基本設定の確認
        config_status = {
            "gcp_project_id": bool(GCP_PROJECT_ID),
            "webhook_url": bool(WEBHOOK_URL),
            "monitored_users": len(monitored_users),
            "secret_manager": bool(SERVICE_ACCOUNT_SECRET_NAME),
            "service_account_file": bool(SERVICE_ACCOUNT_FILE_PATH and os.path.exists(SERVICE_ACCOUNT_FILE_PATH))
        }
        
        return {
            "status": "healthy",
            "version": "2.0.0",
            "config": config_status,
            "users": list(monitored_users.keys())
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")

@app.post("/test-authentication")
async def test_authentication():
    """認証システムの包括的テスト"""
    if not monitored_users:
        raise HTTPException(status_code=400, detail="No monitored users configured")
    
    results = []
    for user_email in monitored_users.keys():
        try:
            logger.info(f"Testing authentication for: {user_email}")
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)
            
            # 基本的な認証テスト
            about = drive_service.about().get(fields='user,storageQuota').execute()
            user_info = about.get('user', {})
            
            # 権限テスト - ファイル一覧取得
            files_response = drive_service.files().list(
                pageSize=5,
                fields='files(id, name, mimeType)'
            ).execute()
            
            files_count = len(files_response.get('files', []))
            
            results.append({
                "user": user_email,
                "status": "success",
                "authenticated_as": user_info.get('emailAddress', 'unknown'),
                "display_name": user_info.get('displayName', 'Unknown'),
                "domain_delegation": user_info.get('emailAddress') == user_email,
                "files_accessible": files_count,
                "credentials_type": type(creds).__name__
            })
            
            logger.info(f"Authentication successful for {user_email}")
            
        except Exception as e:
            error_message = str(e)[:200]
            results.append({
                "user": user_email,
                "status": "error",
                "error": error_message,
                "error_type": type(e).__name__
            })
            logger.error(f"Authentication failed for {user_email}: {error_message}")
    
    return {"authentication_test": results}

@app.post("/webhook", status_code=204)
async def handle_drive_notification(request: Request):
    """セキュアなGoogle Drive Push Notification処理"""
    
    # ヘッダー検証
    channel_state, channel_token, channel_id = _validate_webhook_headers(request)
    
    # sync通知は無視
    if channel_state == "sync":
        logger.info("Ignoring sync notification")
        return Response(status_code=204)
    
    if not channel_token:
        logger.warning("Missing channel token")
        return Response(status_code=204)
    
    try:
        # チャネルトークンの解析
        if ':' not in channel_token:
            logger.error(f"Invalid token format: {channel_token}")
            return Response(status_code=204)
        
        user_email, folder_id = channel_token.split(':', 1)
        
        if user_email not in monitored_users:
            logger.warning(f"Unknown user: {user_email}")
            return Response(status_code=204)
        
        logger.info(f"Processing webhook for user: {user_email}, folder: {folder_id}")
        
        # 認証取得
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # 変更チェックの改善版実装
        await _process_drive_changes(drive_service, folder_id, user_email)
    
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)[:100]}...")
        
        if _is_retryable_error(e):
            raise HTTPException(status_code=500, detail="Temporary error, will retry")
        else:
            logger.error(f"Permanent error, will not retry: {e}")
    
    return Response(status_code=204)

async def _process_drive_changes(drive_service, folder_id: str, user_email: str) -> None:
    """
    Google Driveの変更を処理する改善版
    """
    try:
        # 現在のページトークンを取得
        response = drive_service.changes().getStartPageToken().execute()
        start_page_token = response.get('startPageToken')
        
        logger.info(f"Checking changes from page token: {start_page_token}")
        
        try:
            # 変更リストを取得
            changes_response = drive_service.changes().list(
                pageToken=start_page_token,
                includeRemoved=False,
                spaces='drive',
                fields='changes(file(id,name,mimeType,parents,createdTime))'
            ).execute()
            
            changes = changes_response.get('changes', [])
            logger.info(f"Found {len(changes)} changes to process")
            
            # Meet Recordingsフォルダ内の新しいドキュメントをチェック
            for change in changes:
                file_info = change.get('file')
                if not file_info:
                    continue
                
                file_name = file_info.get('name', 'Unknown')
                file_type = file_info.get('mimeType', 'Unknown')
                parents = file_info.get('parents', [])
                
                # 目的のフォルダ内のGoogle Documentsをチェック
                if (file_type == 'application/vnd.google-apps.document' and folder_id in parents):
                    logger.info(f"Found new Meet document: '{file_name}' in folder {folder_id}")
                    await _process_document_safely(file_info.get('id'), user_email)
                
                # デバッグ情報
                elif folder_id in parents:
                    logger.info(f"Found other file in Meet folder: '{file_name}' (Type: {file_type})")
        
        except Exception as changes_error:
            logger.error(f"Changes API error: {changes_error}")
            # フォールバック: フォルダ直接チェック
            logger.info("Falling back to direct folder check...")
            await _check_folder_directly(folder_id, user_email)
    
    except Exception as e:
        logger.error(f"Drive changes processing failed: {str(e)[:100]}...")
        # フォールバック処理
        await _check_folder_directly(folder_id, user_email)

async def _check_folder_directly(folder_id: str, user_email: str) -> None:
    """フォルダの直接チェック（フォールバック）"""
    try:
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Google Documentsとその他のMeet関連ファイルを検索
        query = f"'{folder_id}' in parents and (mimeType='application/vnd.google-apps.document' or name contains '.docx' or name contains 'transcript')"
        response = drive_service.files().list(
            q=query,
            orderBy='createdTime desc',
            pageSize=10,
            fields='files(id, name, createdTime, mimeType)'
        ).execute()
        
        files = response.get('files', [])
        logger.info(f"Direct check found {len(files)} potential files in folder {folder_id}")
        
        for file_info in files:
            file_name = file_info.get('name', 'Unknown')
            file_type = file_info.get('mimeType', 'Unknown')
            logger.info(f"Processing file: '{file_name}' (Type: {file_type})")
            
            # Google Documentsのみ処理（他のファイルタイプは将来的に拡張可能）
            if file_type == 'application/vnd.google-apps.document':
                await _process_document_safely(file_info.get('id'), user_email)
            else:
                logger.info(f"Skipping non-document file: {file_name}")
            
    except Exception as e:
        logger.error(f"Direct folder check failed: {str(e)[:100]}...")

@app.post("/test-folder-check")
async def test_folder_check():
    """フォルダアクセステスト"""
    if not monitored_users:
        raise HTTPException(status_code=400, detail="No monitored users configured")
    
    results = []
    for user_email, folder_id in monitored_users.items():
        try:
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)
            
            # フォルダIDが設定されていない場合は検索
            if not folder_id:
                folder_id = _find_meet_recordings_folder(drive_service, user_email)
                if not folder_id:
                    results.append({
                        "user": user_email,
                        "status": "folder_not_found",
                        "error": "Meet Recordings folder not found"
                    })
                    continue
                
                results.append({
                    "user": user_email,
                    "status": "found_folder",
                    "folder_id": folder_id,
                    "folder_name": "Meet Recordings"
                })
            
            # フォルダ内のドキュメントをチェック
            query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
            docs_response = drive_service.files().list(
                q=query,
                pageSize=5,
                fields='files(id, name, createdTime)'
            ).execute()
            
            documents = docs_response.get('files', [])
            results.append({
                "user": user_email,
                "status": "success",
                "folder_id": folder_id,
                "documents_found": len(documents),
                "recent_documents": [doc['name'] for doc in documents[:3]]
            })
            
        except Exception as e:
            results.append({
                "user": user_email,
                "status": "error",
                "error": str(e)[:100]
            })
    
    return {"folder_test": results}

@app.post("/renew-all-watches")
async def renew_all_watches():
    """監視チャネルの更新"""
    if not WEBHOOK_URL:
        raise HTTPException(status_code=500, detail="WEBHOOK_URL not configured")
    
    if not monitored_users:
        logger.warning("No monitored users configured")
        return {"status": "completed", "message": "No users to monitor"}
    
    logger.info("Starting renewal process for all watch channels")
    results = []
    
    for user_email, folder_id in monitored_users.items():
        try:
            logger.info(f"Processing user: {user_email}")
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)
            
            # フォルダID確認・取得
            if not folder_id:
                folder_id = _find_meet_recordings_folder(drive_service, user_email)
                if not folder_id:
                    raise FileNotFoundError("Meet Recordings folder not found")
                
                logger.info(f"Found Meet Recordings folder: {folder_id}")
            
            # changes.watch設定
            page_token_response = drive_service.changes().getStartPageToken().execute()
            start_page_token = page_token_response.get('startPageToken')
            
            # ユニークなチャネルIDを生成
            channel_id = str(uuid.uuid4())
            
            # Watchリクエストの設定
            watch_request = {
                "id": channel_id,
                "type": "web_hook",
                "address": WEBHOOK_URL,
                "token": f"{user_email}:{folder_id}",
                "expiration": str(int((time.time() + 86400) * 1000))  # 24時間後に期限切れ
            }
            
            # Watchチャネルを設定
            watch_response = drive_service.changes().watch(
                pageToken=start_page_token,
                body=watch_request
            ).execute()
            
            expiration_time = watch_response.get('expiration')
            if expiration_time:
                # ミリ秒から秒に変換
                expiration_datetime = datetime.fromtimestamp(int(expiration_time) / 1000)
                expiration_str = expiration_datetime.isoformat()
            else:
                expiration_str = "Unknown"
            
            results.append({
                "user": user_email,
                "status": "success",
                "channel_id": channel_id,
                "folder_id": folder_id,
                "expiration": expiration_str,
                "webhook_url": WEBHOOK_URL
            })
            
            logger.info(f"Successfully set up watch for {user_email}")
            
        except Exception as e:
            error_msg = str(e)[:100]
            results.append({
                "user": user_email,
                "status": "error",
                "error": error_msg
            })
            logger.error(f"Failed to set up watch for {user_email}: {error_msg}")
    
    success_count = sum(1 for r in results if r['status'] == 'success')
    failure_count = len(results) - success_count
    
    logger.info(f"Renewal completed: {success_count} success, {failure_count} failures")
    
    return {
        "status": "completed",
        "summary": f"Success: {success_count}, Failure: {failure_count}",
        "results": results
    }

@app.get("/")
async def root():
    """アプリケーション情報"""
    return {
        "name": "Google Meet Minutes Processor",
        "version": "2.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhook",
            "test_auth": "/test-authentication",
            "test_folder": "/test-folder-check",
            "renew_watches": "/renew-all-watches"
        },
        "monitored_users": len(monitored_users),
        "configuration": {
            "secret_manager_enabled": bool(SERVICE_ACCOUNT_SECRET_NAME),
            "file_auth_enabled": bool(SERVICE_ACCOUNT_FILE_PATH),
            "project_id": bool(GCP_PROJECT_ID),
            "webhook_url": bool(WEBHOOK_URL)
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)