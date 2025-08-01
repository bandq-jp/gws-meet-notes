# main.py
# FastAPIアプリケーションのメインファイル

import os
import uuid

from fastapi import FastAPI, Request, Response, HTTPException
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.auth

# --- 設定値 -------------------------------------------------------------------

# 環境変数から設定を読み込む
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Cloud RunのURL + /webhook
SERVICE_ACCOUNT_EMAIL = os.getenv('SERVICE_ACCOUNT_EMAIL')  # ドメイン全体の委任が設定されたサービスアカウント

# Google APIのスコープ
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

# 監視対象ユーザーの設定（環境変数から取得）
MONITORED_USERS = {
    # ユーザーのメールアドレス: Meet RecordingsフォルダのID
    # 例: "user@example.com": "1234567890abcdef"
}

# 環境変数から監視対象ユーザーを読み込む
# 形式: "email1:folderid1,email2:folderid2" または "email1,email2" (フォルダIDは自動検索)
users_config = os.getenv('MONITORED_USERS', '')
if users_config:
    for user_config in users_config.split(','):
        user_config = user_config.strip()
        if ':' in user_config:
            # フォルダID指定あり
            email, folder_id = user_config.split(':', 1)
            MONITORED_USERS[email] = folder_id
        else:
            # メールアドレスのみ（フォルダIDは後で自動検索）
            MONITORED_USERS[user_config] = None

# FastAPIアプリケーションのインスタンス化
app = FastAPI(
    title="Google Meet Minutes Processor",
    description="Receives notifications from Google Drive and processes meeting minutes.",
)


# --- 認証ヘルパー -------------------------------------------------------------

def get_impersonated_credentials(subject_email: str):
    """
    指定されたユーザーになりすますための認証情報を生成する。
    
    注意：Google Workspace APIでドメイン全体の委任を使用するには、
    サービスアカウントキーファイルが必要です。Cloud Runの実行時認証では
    ドメイン全体の委任ができません。
    
    代替案：
    1. サービスアカウントキーファイルを使用（最も確実）
    2. 個別ユーザー認証（OAuth2）
    3. 特定の制限された範囲でのアクセス
    """
    try:
        print(f"Getting credentials for user: {subject_email}")
        
        # 方法1: Secret Managerからサービスアカウントキーを取得
        secret_name = os.getenv('SERVICE_ACCOUNT_SECRET_NAME')
        if secret_name and GCP_PROJECT_ID:
            try:
                from google.cloud import secretmanager
                
                print(f"Fetching service account key from Secret Manager: {secret_name}")
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                
                # Secret Managerからキーデータを取得
                key_data = response.payload.data.decode("UTF-8")
                
                # デバッグ: キーデータの最初の部分のみ表示
                print("Successfully fetched service account key from Secret Manager")
                
                # JSONデータから認証情報を作成
                import json
                key_info = json.loads(key_data)
                credentials = service_account.Credentials.from_service_account_info(
                    key_info, scopes=SCOPES
                )
                
                print("Successfully loaded service account credentials with domain delegation")
                return credentials.with_subject(subject_email)
                
            except Exception as secret_error:
                print(f"Failed to load from Secret Manager: {secret_error}")
        else:
            print(f"No secret name provided. SECRET_NAME: {secret_name}, PROJECT_ID: {GCP_PROJECT_ID}")
        
        # 方法2: 環境変数でサービスアカウントキーファイルパスが指定されている場合
        service_account_file = os.getenv('SERVICE_ACCOUNT_FILE_PATH')
        if service_account_file and os.path.exists(service_account_file):
            print(f"Using service account file: {service_account_file}")
            credentials = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=SCOPES
            )
            return credentials.with_subject(subject_email)
        
        # 方法2: Cloud Runのデフォルト認証（制限あり）
        print("Using Cloud Run default credentials (limited access)")
        credentials, project_id = google.auth.default(scopes=SCOPES)
        print(f"Service account: {getattr(credentials, 'service_account_email', 'Unknown')}")
        
        # ドメイン全体の委任はできないが、とりあえず試行
        if hasattr(credentials, 'with_subject'):
            print(f"Attempting domain-wide delegation for: {subject_email}")
            return credentials.with_subject(subject_email)
        else:
            print("Warning: Domain-wide delegation not available with Cloud Run default credentials.")
            print("Consider using a service account key file for full functionality.")
            
            # 制限された認証情報を返す（一部機能のみ動作）
            return credentials
                
    except Exception as e:
        print(f"Authentication error: {e}")
        print("\nTo fix this issue:")
        print("1. Create a service account key file with domain-wide delegation")
        print("2. Upload it to your Cloud Run container")
        print("3. Set SERVICE_ACCOUNT_FILE_PATH environment variable")
        print("4. Or configure OAuth2 for individual user consent")
        raise Exception(f"Authentication failed: {e}")


# --- APIクライアント生成は各関数内で実装 ---


# --- エンドポイント ------------------------------------------------------------

@app.post("/webhook", status_code=204)
async def handle_drive_notification(request: Request):
    """
    Google Driveからの直接Push Notificationを受け取るエンドポイント
    """
    # --- 1. リクエストヘッダーから情報を取得 ---
    channel_state = request.headers.get("X-Goog-Resource-State")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    channel_token = request.headers.get("X-Goog-Channel-Token")
    channel_id = request.headers.get("X-Goog-Channel-ID")

    print(f"Received notification: state={channel_state}, resource={resource_id}, token={channel_token}, channel={channel_id}")

    # sync通知は無視（初回設定時の確認通知）
    if channel_state == "sync":
        print("Ignoring sync notification")
        return Response(status_code=204)

    if not channel_token:
        print("Missing channel token")
        return Response(status_code=204)

    try:
        # --- 2. チャネルトークンからユーザー情報を取得 ---
        # トークンはemail:folder_id形式
        if ':' not in channel_token:
            print(f"Invalid channel token format: {channel_token}")
            return Response(status_code=204)
            
        user_email, meet_recordings_folder_id = channel_token.split(':', 1)
        
        if not user_email or not meet_recordings_folder_id:
            print(f"Missing user email or folder ID in token: {channel_token}")
            return Response(status_code=204)

        # --- 3. ユーザーになりすましてAPI呼び出し ---
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # --- 4. changes.listで最新の変更をチェック ---
        # シンプルにするため、現在のページトークンから開始
        response = drive_service.changes().getStartPageToken().execute()
        start_page_token = response.get('startPageToken')
        
        # 最近の変更をチェック（直近の変更のみ）
        try:
            response = drive_service.changes().list(
                pageToken=start_page_token,
                includeRemoved=False,
                spaces='drive',
                fields='changes(file(id,name,mimeType,parents))'
            ).execute()
            
            # --- 5. Meet Recordingsフォルダ内のGoogleドキュメントをチェック ---
            for change in response.get('changes', []):
                file_info = change.get('file')
                if not file_info:
                    continue
                    
                # Googleドキュメントで、Meet Recordingsフォルダ内のファイルかチェック
                if (file_info.get('mimeType') == 'application/vnd.google-apps.document' and
                    meet_recordings_folder_id in file_info.get('parents', [])):
                    
                    print(f"Found new Google Doc in Meet Recordings: {file_info.get('name')}")
                    await process_document(file_info.get('id'), user_email)
        except Exception as e:
            print(f"Error checking changes: {e}")
            # フォールバック: フォルダ内のドキュメントを直接チェック
            await check_folder_directly(meet_recordings_folder_id, user_email)
            
    except Exception as e:
        print(f"Error processing notification: {e}")
        # 一時的なエラーの場合は500を返してリトライさせる
        # 永続的なエラーの場合は204を返してリトライを停止
        raise HTTPException(status_code=500, detail=str(e))
    
    return Response(status_code=204)


async def process_document(file_id: str, user_email: str):
    """
    Googleドキュメントの内容を処理する
    """
    try:
        creds = get_impersonated_credentials(user_email)
        docs_service = build('docs', 'v1', credentials=creds)
        
        # ドキュメントの内容を取得
        document = docs_service.documents().get(documentId=file_id).execute()
        
        # テキストを抽出
        content_text = ""
        for content in document.get('body', {}).get('content', []):
            if 'paragraph' in content:
                for element in content.get('paragraph', {}).get('elements', []):
                    if 'textRun' in element:
                        content_text += element.get('textRun', {}).get('content', '')
        
        # ドキュメントタイトルとテキストの最初の50文字をログ出力
        title = document.get('title', 'Untitled')
        content_preview = content_text.strip()[:50]
        if len(content_text.strip()) > 50:
            content_preview += "..."
            
        print(f"📄 NEW DOCUMENT: '{title}'")
        print(f"📝 PREVIEW (50 chars): {content_preview}")
        print(f"👤 USER: {user_email}")
        print("---")
        
    except Exception as e:
        print(f"Error processing document {file_id}: {e}")


async def check_folder_directly(folder_id: str, user_email: str):
    """
    Meet Recordingsフォルダを直接チェックして新しいドキュメントを探す
    """
    try:
        creds = get_impersonated_credentials(user_email)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # フォルダ内のドキュメントを最新順で取得
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
        response = drive_service.files().list(
            q=query,
            orderBy='createdTime desc',
            pageSize=5,  # 最新の5件のみ
            fields='files(id, name, createdTime)'
        ).execute()
        
        for file_info in response.get('files', []):
            print(f"Checking document: {file_info.get('name')}")
            await process_document(file_info.get('id'), user_email)
            
    except Exception as e:
        print(f"Error checking folder directly: {e}")


@app.post("/renew-all-watches")
async def renew_all_watches():
    """
    全監視対象ユーザーのchanges.watchチャネルを更新するエンドポイント
    Cloud Schedulerから定期的に呼び出されることを想定（24時間ごと）
    """
    print("Starting renewal process for all watch channels...")
    print(f"MONITORED_USERS: {MONITORED_USERS}")
    print(f"WEBHOOK_URL: {WEBHOOK_URL}")
    
    if not WEBHOOK_URL:
        raise HTTPException(status_code=500, detail="WEBHOOK_URL environment variable not set")
        
    if not MONITORED_USERS:
        print("No monitored users configured")
        return {"status": "completed", "summary": "No users to monitor", "success": 0, "failure": 0}
    
    success_count = 0
    failure_count = 0

    for user_email, folder_id in MONITORED_USERS.items():
        try:
            print(f"Processing user: {user_email}")
            creds = get_impersonated_credentials(user_email)
            drive_service = build('drive', 'v3', credentials=creds)

            # --- 1. フォルダIDの確認・取得 ---
            if not folder_id:
                # フォルダIDが設定されていない場合は検索
                print(f"Searching for 'Meet Recordings' folder for user: {user_email}")
                q = "name='Meet Recordings' and mimeType='application/vnd.google-apps.folder'"
                response = drive_service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
                files = response.get('files', [])
                if not files:
                    raise FileNotFoundError(f"'Meet Recordings' folder not found for user {user_email}")
                folder_id = files[0].get('id')
                print(f"Found 'Meet Recordings' folder with ID: {folder_id}")
                # メモリ上のMONITORED_USERSを更新
                MONITORED_USERS[user_email] = folder_id
            
            print(f"Using 'Meet Recordings' folder ID: {folder_id}")

            # --- 2. 現在のページトークンを取得 ---
            response = drive_service.changes().getStartPageToken().execute()
            start_page_token = response.get('startPageToken')
            
            # --- 3. 新しいchanges.watchを設定 ---
            channel_id = str(uuid.uuid4())
            # トークンにuser_email:folder_idを設定
            token = f"{user_email}:{folder_id}"
            
            watch_request = {
                "id": channel_id,
                "type": "web_hook",
                "address": WEBHOOK_URL,
                "token": token
            }
            
            watch_response = drive_service.changes().watch(
                pageToken=start_page_token,
                body=watch_request
            ).execute()
            
            print(f"Successfully set up watch for user: {user_email}, channel: {channel_id}")
            print(f"Watch expires at: {watch_response.get('expiration')}")
            success_count += 1
        
        except Exception as e:
            print(f"ERROR: Failed to set up watch for user {user_email}. Reason: {e}")
            failure_count += 1
            
    summary = f"Renewal process finished. Success: {success_count}, Failure: {failure_count}"
    print(summary)
    return {"status": "completed", "summary": summary, "success": success_count, "failure": failure_count}

@app.get("/")
def read_root():
    return {
        "message": "Google Meet Minutes Processor is running.",
        "webhook_url": WEBHOOK_URL,
        "service_account_email": SERVICE_ACCOUNT_EMAIL,
        "monitored_users": list(MONITORED_USERS.keys()) if MONITORED_USERS else [],
        "gcp_project_id": GCP_PROJECT_ID
    }


@app.post("/test-folder-check")
async def test_folder_check():
    """
    テスト用エンドポイント: 各ユーザーのMeet Recordingsフォルダを直接チェック
    """
    if not MONITORED_USERS:
        return {"error": "No monitored users configured"}
    
    results = []
    for user_email, folder_id in MONITORED_USERS.items():
        try:
            await check_folder_directly(folder_id, user_email)
            results.append({"user": user_email, "status": "success"})
        except Exception as e:
            results.append({"user": user_email, "status": "error", "error": str(e)})
    
    return {"results": results}