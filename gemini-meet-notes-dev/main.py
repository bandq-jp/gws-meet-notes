# main.py
# Google Meet Minutes Processor - Secure Cloud Run Implementation
# セキュアなGoogle Drive監視アプリケーション

import os
import uuid
import json
import logging
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
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
        
        logger.info(f"Fetching credentials from Secret Manager: {secret_name}")
        response = client.access_secret_version(request={"name": name})
        
        key_data = response.payload.data.decode("UTF-8")
        key_info = json.loads(key_data)
        
        credentials = service_account.Credentials.from_service_account_info(
            key_info, scopes=SCOPES
        )
        
        logger.info("Successfully loaded service account from Secret Manager")
        return credentials.with_subject(subject_email)
        
    except Exception as e:
        logger.error(f"Failed to load from Secret Manager: {str(e)[:100]}...")
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
    
    # 方法1: Secret Manager（推奨）
    if SERVICE_ACCOUNT_SECRET_NAME and GCP_PROJECT_ID:
        try:
            return _get_credentials_from_secret_manager(SERVICE_ACCOUNT_SECRET_NAME, subject_email)
        except Exception as e:
            logger.error(f"Secret Manager authentication failed: {str(e)[:100]}...")
    
    # 方法2: サービスアカウントファイル（開発用）
    if SERVICE_ACCOUNT_FILE_PATH:
        try:
            return _get_credentials_from_file(SERVICE_ACCOUNT_FILE_PATH, subject_email)
        except Exception as e:
            logger.error(f"File-based authentication failed: {str(e)[:100]}...")
    
    # 方法3: デフォルト認証（制限あり）
    logger.warning("Falling back to default credentials - limited functionality")
    return _get_default_credentials_with_impersonation(subject_email)

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
    """認証システムのテスト"""
    if not monitored_users:
        raise HTTPException(status_code=400, detail="No monitored users configured")
    
    results = []
    for user_email in monitored_users.keys():
        try:
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)
            
            # 簡単なAPI呼び出しでテスト
            about = drive_service.about().get(fields='user').execute()
            user_info = about.get('user', {})
            
            results.append({
                "user": user_email,
                "status": "success",
                "authenticated_as": user_info.get('emailAddress', 'unknown')
            })
            
        except Exception as e:
            results.append({
                "user": user_email,
                "status": "error",
                "error": str(e)[:100]
            })
    
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
        
        # 認証取得
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # 変更をチェック
        response = drive_service.changes().getStartPageToken().execute()
        start_page_token = response.get('startPageToken')
        
        try:
            changes_response = drive_service.changes().list(
                pageToken=start_page_token,
                includeRemoved=False,
                spaces='drive',
                fields='changes(file(id,name,mimeType,parents))'
            ).execute()
            
            # Meet Recordingsフォルダ内のGoogleドキュメントをチェック
            for change in changes_response.get('changes', []):
                file_info = change.get('file')
                if not file_info:
                    continue
                
                if (file_info.get('mimeType') == 'application/vnd.google-apps.document' and
                    folder_id in file_info.get('parents', [])):
                    
                    logger.info(f"Found new document: {file_info.get('name')}")
                    await _process_document_safely(file_info.get('id'), user_email)
        
        except Exception as changes_error:
            logger.error(f"Changes API error: {changes_error}")
            # フォールバック: フォルダ直接チェック
            await _check_folder_directly(folder_id, user_email)
    
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)[:100]}...")
        
        if _is_retryable_error(e):
            raise HTTPException(status_code=500, detail="Temporary error, will retry")
        else:
            logger.error(f"Permanent error, will not retry: {e}")
    
    return Response(status_code=204)

async def _check_folder_directly(folder_id: str, user_email: str) -> None:
    """フォルダの直接チェック（フォールバック）"""
    try:
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
        response = drive_service.files().list(
            q=query,
            orderBy='createdTime desc',
            pageSize=5,
            fields='files(id, name, createdTime)'
        ).execute()
        
        for file_info in response.get('files', []):
            logger.info(f"Direct check found document: {file_info.get('name')}")
            await _process_document_safely(file_info.get('id'), user_email)
            
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
                q = "name='Meet Recordings' and mimeType='application/vnd.google-apps.folder'"
                response = drive_service.files().list(q=q, fields='files(id, name)').execute()
                files = response.get('files', [])
                
                if files:
                    folder_id = files[0]['id']
                    results.append({
                        "user": user_email,
                        "status": "found_folder",
                        "folder_id": folder_id,
                        "folder_name": files[0]['name']
                    })
                else:
                    results.append({
                        "user": user_email,
                        "status": "folder_not_found",
                        "error": "Meet Recordings folder not found"
                    })
                    continue
            
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
                q = "name='Meet Recordings' and mimeType='application/vnd.google-apps.folder'"
                response = drive_service.files().list(q=q, fields='files(id, name)').execute()
                files = response.get('files', [])
                
                if not files:
                    raise FileNotFoundError("Meet Recordings folder not found")
                
                folder_id = files[0]['id']
                logger.info(f"Found Meet Recordings folder: {folder_id}")
            
            # changes.watch設定
            page_token_response = drive_service.changes().getStartPageToken().execute()
            start_page_token = page_token_response.get('startPageToken')
            
            channel_id = str(uuid.uuid4())
            watch_request = {
                "id": channel_id,
                "type": "web_hook",
                "address": WEBHOOK_URL,
                "token": f"{user_email}:{folder_id}"
            }
            
            watch_response = drive_service.changes().watch(
                pageToken=start_page_token,
                body=watch_request
            ).execute()
            
            results.append({
                "user": user_email,
                "status": "success",
                "channel_id": channel_id,
                "folder_id": folder_id,
                "expiration": watch_response.get('expiration')
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
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhook",
            "test_auth": "/test-authentication",
            "test_folder": "/test-folder-check",
            "renew_watches": "/renew-all-watches"
        },
        "monitored_users": len(monitored_users)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)