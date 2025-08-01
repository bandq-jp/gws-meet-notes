# main.py
# FastAPIアプリケーションのメインファイル (Firestore不使用版)

import base64
import json
import os
import uuid
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
import google.auth

# --- 設定値 -------------------------------------------------------------------

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
PUBSUB_TOPIC_NAME = os.getenv('PUBSUB_TOPIC_NAME')
# 環境変数から監視対象ユーザーをカンマ区切りで取得
MONITORED_USERS = os.getenv('MONITORED_USERS', '')

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

app = FastAPI(
    title="Google Meet Minutes Processor",
    description="Receives notifications from Google Drive via Pub/Sub and processes meeting minutes.",
)

# --- Pydanticモデル (変更なし) ---------------------------------------------

class PubSubMessage(BaseModel):
    attributes: Dict[str, str]
    data: str

class PubSubRequest(BaseModel):
    message: PubSubMessage
    subscription: str

# --- 認証ヘルパー (変更なし) -------------------------------------------------

def get_impersonated_credentials(subject_email: str):
    """指定されたユーザーになりすますための認証情報を生成する。"""
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds.with_subject(subject_email)

# --- エンドポイント ------------------------------------------------------------

@app.post("/webhook", status_code=204)
async def handle_drive_notification(body: PubSubRequest):
    """
    Pub/SubからのPush通知を受け取るエンドポイント。(この関数は変更なし)
    """
    attributes = body.message.attributes
    channel_state = attributes.get("X-Goog-Resource-State")
    file_id = attributes.get("X-Goog-Resource-ID")
    user_email = attributes.get("X-Goog-Channel-Token")

    print(f"Received notification for user: {user_email}, file: {file_id}, state: {channel_state}")

    if channel_state == "sync":
        print("Sync message received. No action needed.")
        return Response(status_code=204)
        
    if channel_state not in ("add", "update") or not user_email or not file_id:
        print("Ignoring notification due to irrelevant state or missing attributes.")
        return Response(status_code=204)

    try:
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = drive_service.files().get(
            fileId=file_id, fields='mimeType, name, trashed'
        ).execute()

        if file_metadata.get('trashed'):
             print(f"File '{file_metadata.get('name')}' is in trash. Skipping.")
             return Response(status_code=204)

        if file_metadata.get('mimeType') != 'application/vnd.google-apps.folder+vnd.google-apps.document':
            print(f"File '{file_metadata.get('name')}' is not a Google Doc. MIME type: {file_metadata.get('mimeType')}. Skipping.")
            return Response(status_code=204)

        print(f"Processing Google Doc: '{file_metadata.get('name')}' for user {user_email}")

        docs_service = build('docs', 'v1', credentials=creds)
        document = docs_service.documents().get(documentId=file_id).execute()
        
        content_text = "".join(
            element.get('textRun', {}).get('content', '')
            for content in document.get('body', {}).get('content', [])
            if 'paragraph' in content
            for element in content.get('paragraph', {}).get('elements', [])
            if 'textRun' in element
        )

        # --- ここで取得したテキストをログに出力 ---
        print("--- Document Content ---")
        print(content_text.strip())
        print("------------------------")

    except HttpError as e:
        print(f"ERROR: API HttpError for user {user_email}, file {file_id}. Reason: {e}")
        if e.resp.status in [403, 404]:
            return Response(status_code=204)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"ERROR: Failed to process notification for user {user_email}, file {file_id}. Reason: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return Response(status_code=204)


@app.post("/renew-all-watches")
async def renew_all_watches():
    """
    環境変数で指定された全ユーザーのWatchチャネルを更新する。
    """
    if not PUBSUB_TOPIC_NAME:
        raise HTTPException(status_code=500, detail="PUBSUB_TOPIC_NAME environment variable is not set.")
    if not MONITORED_USERS:
        raise HTTPException(status_code=500, detail="MONITORED_USERS environment variable is not set or empty.")

    # 環境変数からメールアドレスのリストを作成
    user_list = [email.strip() for email in MONITORED_USERS.split(',') if email.strip()]
    
    print(f"Starting renewal process for watch channels. Target users: {user_list}")
    success_count = 0
    failure_count = 0

    for user_email in user_list:
        try:
            print(f"Processing user: {user_email}")
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)

            # --- 1. 'Meet Recordings' フォルダのIDを取得 ---
            q = "name='Meet Recordings' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            response = drive_service.files().list(
                q=q, spaces='drive', fields='files(id, name)', pageSize=1
            ).execute()
            
            files = response.get('files', [])
            if not files:
                raise FileNotFoundError(f"'Meet Recordings' folder not found for user {user_email}")
            folder_id = files[0].get('id')
            
            print(f"Found 'Meet Recordings' folder with ID: {folder_id}")

            # --- 2. watchリクエストを送信 ---
            channel_id = str(uuid.uuid4())
            watch_request_body = {
                "id": channel_id,
                "type": "web_hook",
                "address": f"https://www.googleapis.com/drive/v3/changes/watch",
                "token": user_email,
                "payload": True,
            }
            
            drive_service.files().watch(fileId=folder_id, body=watch_request_body).execute()
            
            print(f"Successfully renewed watch channel for user: {user_email} on folder {folder_id}")
            success_count += 1
        
        except Exception as e:
            print(f"ERROR: Failed to renew watch for user {user_email}. Reason: {e}")
            failure_count += 1
            
    summary = f"Renewal process finished. Success: {success_count}, Failure: {failure_count}"
    print(summary)
    return {"status": "completed", "summary": summary}


@app.get("/")
def read_root():
    return {"message": "Google Meet Minutes Processor is running."}