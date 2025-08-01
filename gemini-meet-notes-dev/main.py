# main.py
# FastAPIアプリケーションのメインファイル

import os
import uuid
from typing import Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from google.cloud import firestore
import google.auth

# --- 設定値 -------------------------------------------------------------------

# 環境変数から設定を読み込む
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE_PATH', 'path/to/your/service-account-key.json') # ローカルテスト用
PUBSUB_TOPIC_NAME = os.getenv('PUBSUB_TOPIC_NAME') # projects/your-project-id/topics/your-topic-name

# Google APIのスコープ
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

# Firestoreクライアントの初期化
db = firestore.Client()

# FastAPIアプリケーションのインスタンス化
app = FastAPI(
    title="Google Meet Minutes Processor",
    description="Receives notifications from Google Drive and processes meeting minutes.",
)


# --- 認証ヘルパー -------------------------------------------------------------

def get_impersonated_credentials(subject_email: str):
    """
    指定されたユーザーになりすますための認証情報を生成する。
    Cloud Runのランタイムサービスアカウントを利用することを想定。
    """
    # Cloud Run環境では、`google.auth.default()`でランタイムのサービスアカウント認証情報を取得
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds.with_subject(subject_email)


# --- APIクライアント生成 (Dependency Injection) -----------------------------

def get_drive_service(creds: Any = Depends(get_impersonated_credentials)) -> Resource:
    """Google Drive APIクライアントを生成する"""
    return build('drive', 'v3', credentials=creds)

def get_docs_service(creds: Any = Depends(get_impersonated_credentials)) -> Resource:
    """Google Docs APIクライアントを生成する"""
    return build('docs', 'v1', credentials=creds)


# --- エンドポイント ------------------------------------------------------------

@app.post("/webhook", status_code=204)
async def handle_drive_notification(request: Request):
    """
    Eventarc経由でPub/Subからの通知を受け取るエンドポイント (FR-01, FR-02, FR-06)
    """
    # --- 1. リクエストヘッダーから情報を取得 ---
    # Google DriveからのPush Notificationは、ヘッダーに情報を含む
    channel_state = request.headers.get("X-Goog-Resource-State")
    file_id = request.headers.get("X-Goog-Resource-ID")
    # watch登録時にtokenとして設定したユーザーメールアドレスを取得
    user_email = request.headers.get("X-Goog-Channel-Token")

    print(f"Received notification for user: {user_email}, file: {file_id}, state: {channel_state}")

    # ファイル追加・更新以外の通知や、必要なヘッダーがない場合は無視
    if channel_state not in ("add", "update") or not user_email or not file_id:
        print("Ignoring notification due to irrelevant state or missing headers.")
        return Response(status_code=204)

    try:
        # --- 2. ユーザーになりすましてAPIクライアントを取得 ---
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)

        # --- 3. ファイルがGoogleドキュメントか確認 (FR-06) ---
        file_metadata = drive_service.files().get(
            fileId=file_id, fields='mimeType, name'
        ).execute()

        if file_metadata.get('mimeType') != 'application/vnd.google-g-suite.docs':
            print(f"File '{file_metadata.get('name')}' is not a Google Doc. Skipping.")
            return Response(status_code=204)

        print(f"Processing Google Doc: '{file_metadata.get('name')}' for user {user_email}")

        # --- 4. ドキュメントの内容を取得 (FR-02) ---
        document = docs_service.documents().get(documentId=file_id).execute()
        content_text = ""
        for content in document.get('body', {}).get('content', []):
            if 'paragraph' in content:
                for element in content.get('paragraph', {}).get('elements', []):
                    if 'textRun' in element:
                        content_text += element.get('textRun', {}).get('content', '')

        # --- 5. 取得したテキストを処理 ---
        # ここではログに出力するだけだが、実際にはここでDB保存や別APIへの送信などを行う
        print("--- Document Content ---")
        print(content_text.strip())
        print("------------------------")

    except Exception as e:
        # エラーハンドリング (FR-05)
        print(f"ERROR: Failed to process notification for user {user_email}, file {file_id}. Reason: {e}")
        # エラーを返すとPub/Subがリトライを試みる。永続的なエラーの場合は204を返すことも検討。
        raise HTTPException(status_code=500, detail=str(e))

    return Response(status_code=204)


@app.post("/renew-all-watches")
async def renew_all_watches():
    """
    全監視対象ユーザーのWatchチャネルを更新するエンドポイント (FR-04)
    Cloud Schedulerから定期的に呼び出されることを想定
    """
    print("Starting renewal process for all watch channels...")
    users_ref = db.collection('monitored_users').stream()
    success_count = 0
    failure_count = 0

    for user_doc in users_ref:
        user_data = user_doc.to_dict()
        user_email = user_data.get("email")
        if not user_email:
            continue

        try:
            print(f"Processing user: {user_email}")
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)

            # --- 1. 'Meet Recordings' フォルダのIDを取得 ---
            folder_id = user_data.get('meetRecordingsFolderId')
            if not folder_id:
                # FirestoreにIDがなければ検索して保存
                q = "name='Meet Recordings' and mimeType='application/vnd.google-apps.folder'"
                response = drive_service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
                files = response.get('files', [])
                if not files:
                    raise FileNotFoundError(f"'Meet Recordings' folder not found for user {user_email}")
                folder_id = files[0].get('id')
                # Firestoreドキュメントを更新
                user_doc.reference.update({'meetRecordingsFolderId': folder_id})
            
            print(f"Found 'Meet Recordings' folder with ID: {folder_id}")

            # --- 2. watchリクエストを送信 ---
            channel_id = str(uuid.uuid4()) # 新しい監視ごとにユニークなIDを生成
            watch_request_body = {
                "id": channel_id,
                "type": "web_hook",
                "address": f"https://pubsub.googleapis.com/v1/{PUBSUB_TOPIC_NAME}:publish",
                "token": user_email,  # 通知時にユーザーを特定するためのトークン
            }

            drive_service.files().watch(fileId=folder_id, body=watch_request_body).execute()
            
            print(f"Successfully renewed watch channel for user: {user_email}")
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