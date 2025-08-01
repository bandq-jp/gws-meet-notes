import json
import os
import base64
from datetime import datetime, timezone
from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数から設定を取得
STORAGE_PATH = os.environ.get('STORAGE_PATH', './storage')
ALLOWED_ACCOUNTS = os.environ.get('ALLOWED_ACCOUNTS', '').split(',')

def process_meet_notes(cloud_event):
    """
    Pub/Subからのメッセージを処理して議事録とメタデータを保存
    """
    try:
        # Pub/Subメッセージをデコード
        pubsub_message = base64.b64decode(cloud_event.data['message']['data']).decode('utf-8')
        message_data = json.loads(pubsub_message)
        
        logger.info(f"Processing file: {message_data['file_name']}")
        
        # アカウント制限チェック
        owner_email = message_data.get('owner_email')
        if owner_email not in ALLOWED_ACCOUNTS:
            logger.info(f"Skipping file from non-allowed account: {owner_email}")
            return
        
        # Google APIs初期化
        credentials, _ = default()
        drive_service = build('drive', 'v3', credentials=credentials)
        docs_service = build('docs', 'v1', credentials=credentials)
        calendar_service = build('calendar', 'v3', credentials=credentials)
        
        # ドキュメントの内容を取得
        file_id = message_data['file_id']
        doc_content = get_document_content(docs_service, file_id)
        
        # Meetメタデータを取得
        meet_metadata = extract_meet_metadata(doc_content, calendar_service, owner_email)
        
        # ローカルストレージに保存
        save_to_local_storage(message_data, doc_content, meet_metadata)
        
        logger.info(f"Successfully processed: {message_data['file_name']}")
        
    except Exception as e:
        logger.error(f"Error processing meet notes: {str(e)}")
        raise

def get_document_content(docs_service, file_id):
    """Google Docsの内容を取得"""
    try:
        document = docs_service.documents().get(documentId=file_id).execute()
        
        content = []
        for element in document.get('body', {}).get('content', []):
            if 'paragraph' in element:
                paragraph = element['paragraph']
                paragraph_text = ''
                for text_run in paragraph.get('elements', []):
                    if 'textRun' in text_run:
                        paragraph_text += text_run['textRun']['content']
                content.append(paragraph_text.strip())
        
        return {
            'title': document.get('title', ''),
            'content': content,
            'document_id': file_id,
            'revision_id': document.get('revisionId', ''),
        }
        
    except HttpError as e:
        logger.error(f"Error fetching document content: {str(e)}")
        raise

def extract_meet_metadata(doc_content, calendar_service, owner_email):
    """議事録からMeetメタデータを抽出"""
    metadata = {
        'extracted_at': datetime.now(timezone.utc).isoformat(),
        'meeting_info': {},
        'participants': [],
        'meeting_date': None,
        'meeting_duration': None
    }
    
    try:
        # ドキュメントタイトルから日時情報を抽出
        title = doc_content.get('title', '')
        
        # カレンダーAPIで最近のイベントを検索
        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Meetイベントを探す
        for event in events:
            if 'conferenceData' in event:
                conference_data = event['conferenceData']
                if 'entryPoints' in conference_data:
                    for entry_point in conference_data['entryPoints']:
                        if entry_point.get('entryPointType') == 'video':
                            # Meet イベント発見
                            metadata['meeting_info'] = {
                                'event_id': event['id'],
                                'summary': event.get('summary', ''),
                                'start_time': event['start'].get('dateTime', ''),
                                'end_time': event['end'].get('dateTime', ''),
                                'meet_url': entry_point.get('uri', ''),
                                'organizer': event.get('organizer', {}),
                                'attendees': event.get('attendees', [])
                            }
                            
                            # 参加者情報を抽出
                            metadata['participants'] = [
                                {
                                    'email': attendee.get('email', ''),
                                    'display_name': attendee.get('displayName', ''),
                                    'response_status': attendee.get('responseStatus', ''),
                                    'organizer': attendee.get('organizer', False)
                                }
                                for attendee in event.get('attendees', [])
                            ]
                            break
        
        return metadata
        
    except Exception as e:
        logger.error(f"Error extracting meet metadata: {str(e)}")
        return metadata

def save_to_local_storage(file_data, doc_content, meet_metadata):
    """ローカルストレージに保存"""
    try:
        os.makedirs(STORAGE_PATH, exist_ok=True)
        
        # タイムスタンプベースのファイル名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_id = file_data['file_id']
        
        # 議事録データの保存
        notes_data = {
            'file_info': file_data,
            'document_content': doc_content,
            'meet_metadata': meet_metadata,
            'processed_at': datetime.now(timezone.utc).isoformat()
        }
        
        output_file = os.path.join(STORAGE_PATH, f'meet_notes_{timestamp}_{file_id}.json')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(notes_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved meet notes to: {output_file}")
        
        # インデックスファイルの更新
        update_index_file(output_file, file_data, meet_metadata)
        
    except Exception as e:
        logger.error(f"Error saving to local storage: {str(e)}")
        raise

def update_index_file(file_path, file_data, meet_metadata):
    """インデックスファイルを更新"""
    index_file = os.path.join(STORAGE_PATH, 'index.json')
    
    try:
        # 既存のインデックスを読み込み
        if os.path.exists(index_file):
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
        else:
            index_data = {'files': []}
        
        # 新しいエントリを追加
        index_entry = {
            'file_path': file_path,
            'file_id': file_data['file_id'],
            'file_name': file_data['file_name'],
            'owner_email': file_data['owner_email'],
            'created_time': file_data['created_time'],
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'meeting_summary': meet_metadata['meeting_info'].get('summary', ''),
            'meeting_date': meet_metadata['meeting_info'].get('start_time', ''),
            'participants_count': len(meet_metadata['participants'])
        }
        
        index_data['files'].append(index_entry)
        
        # インデックスファイルを保存
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Updated index file: {index_file}")
        
    except Exception as e:
        logger.error(f"Error updating index file: {str(e)}")
        # インデックス更新に失敗してもメイン処理は続行