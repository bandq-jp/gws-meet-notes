import json
import os
from google.cloud import pubsub_v1
from google.auth import default
from googleapiclient.discovery import build
from flask import Request
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数から設定を取得
PROJECT_ID = os.environ.get('GCP_PROJECT')
PUBSUB_TOPIC = os.environ.get('PUBSUB_TOPIC', 'meet-notes-processing')
ALLOWED_ACCOUNTS = os.environ.get('ALLOWED_ACCOUNTS', '').split(',')

def drive_webhook(request: Request):
    """
    Google Drive Push Notificationのwebhook関数
    Meet Recordingsフォルダ内の新しいファイルを検知してPub/Subに送信
    """
    try:
        # リクエストヘッダーの確認
        channel_id = request.headers.get('X-Goog-Channel-ID')
        resource_id = request.headers.get('X-Goog-Resource-ID')
        resource_state = request.headers.get('X-Goog-Resource-State')
        
        logger.info(f"Received webhook: channel_id={channel_id}, resource_id={resource_id}, state={resource_state}")
        
        if resource_state not in ['update', 'sync']:
            logger.info(f"Ignoring resource state: {resource_state}")
            return 'OK', 200
        
        # Drive APIの初期化
        credentials, _ = default()
        service = build('drive', 'v3', credentials=credentials)
        
        # Meet Recordingsフォルダを検索
        meet_folders = service.files().list(
            q="name='Meet Recordings' and mimeType='application/vnd.google-apps.folder'",
            fields='files(id, name, owners)'
        ).execute()
        
        for folder in meet_folders.get('files', []):
            folder_id = folder['id']
            owners = folder.get('owners', [])
            
            # 指定されたアカウントのフォルダのみを処理
            if not any(owner['emailAddress'] in ALLOWED_ACCOUNTS for owner in owners):
                logger.info(f"Skipping folder owned by non-allowed account")
                continue
            
            # フォルダ内の最近更新されたファイルを取得
            recent_files = service.files().list(
                q=f"parents in '{folder_id}' and mimeType='application/vnd.google-apps.document'",
                orderBy='modifiedTime desc',
                pageSize=10,
                fields='files(id, name, createdTime, modifiedTime, owners, webViewLink)'
            ).execute()
            
            for file_info in recent_files.get('files', []):
                # Pub/Subにメッセージを送信
                message_data = {
                    'file_id': file_info['id'],
                    'file_name': file_info['name'],
                    'created_time': file_info['createdTime'],
                    'modified_time': file_info['modifiedTime'],
                    'owner_email': file_info['owners'][0]['emailAddress'],
                    'web_view_link': file_info['webViewLink'],
                    'folder_id': folder_id
                }
                
                publish_to_pubsub(message_data)
        
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Error processing Drive webhook: {str(e)}")
        return f'Error: {str(e)}', 500

def publish_to_pubsub(message_data):
    """Pub/Subにメッセージを送信"""
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
        
        message_json = json.dumps(message_data)
        data = message_json.encode('utf-8')
        
        future = publisher.publish(topic_path, data)
        message_id = future.result()
        
        logger.info(f"Published message {message_id} to {topic_path}")
        
    except Exception as e:
        logger.error(f"Error publishing to Pub/Sub: {str(e)}")
        raise