# Google Meet録画自動取得システム - 完全修正版

## 🔧 特定された問題と修正内容

### 1. **Secret Manager認証エラーの修正**

**問題点:**
- Secret Managerアクセス時の400エラー  
- 破損したJSON認証情報がログに出力
- 無効なシークレットID形式

**適用した解決策:**
- シークレット名の形式を修正（フルパスではなくシークレット名のみ使用）
- サービスアカウント認証情報の適切なJSON検証を追加
- エラーハンドリングとログ出力の改善（機密データの露出防止）
- 必要フィールドの認証情報検証を追加

### 2. **Meet Recordingsフォルダ検出の改善**

**問題点:**
- 「Meet Recordingsフォルダが見つかりません」エラー
- 日本語等のローカライズされたフォルダ名に非対応
- 限定的な検索機能

**適用した解決策:**
- 多言語対応の`_find_meet_recordings_folder()`を実装
- 様々なフォルダ名をサポート:
  - 'Meet Recordings'（英語）
  - 'Meet 記録'（日本語）
  - 'Meet録画'（日本語代替）
  - 'Google Meet録画'（完全日本語）
  - その他バリエーション
- 「Meet」や「記録」を含むフォルダの広範囲検索フォールバックを実装

### 3. **ドメイン全体委任の問題修正**

**問題点:**
- ドメイン全体委任をサポートしないデフォルト認証情報の使用
- 不適切なサービスアカウント設定
- 機能制限警告

**適用した解決策:**
- 適切なサービスアカウント使用の強制（Secret Manager設定時のデフォルト認証情報へのフォールバック廃止）
- `.with_subject(subject_email)`による適切なドメイン全体委任実装の改善
- 包括的な認証テストの追加
- 委任問題に対するより良いエラーメッセージ

### 4. **Google Drive Watch通知の改善**

**問題点:**
- 非効率な変更検出
- APIエラーに対する不十分なエラーハンドリング
- フォールバック機能の不備

**適用した解決策:**
- 改善された変更検出を持つ`_process_drive_changes()`を実装
- 包括的なファイルタイプフィルタリングを追加
- 直接フォルダチェックによる改善されたフォールバック機能
- より良いログ出力とデバッグ情報
- watchチャネルの有効期限処理を追加

### 5. **全体的なコード品質向上**

**問題点:**
- 限定的なエラーハンドリング
- 基本的な認証テスト
- 設定検証の不備

**適用した解決策:**
- 詳細な結果を持つ強化された認証テスト
- 改善されたヘルスチェックエンドポイント
- より良い設定ステータス報告
- 全体を通した包括的なエラーハンドリング

## 🚀 デプロイ手順

### 1. **Secret Managerの設定確認**

```bash
# シークレットが存在するかチェック
gcloud secrets describe service-account-key --project=bandq-dx

# 存在しない場合は作成
gcloud secrets create service-account-key \
    --data-file=path/to/your-service-account-key.json \
    --project=bandq-dx
```

### 2. **サービスアカウントとドメイン全体委任の確認**

1. **Google Cloud Consoleにて:**
   - IAM管理 > サービスアカウントに移動
   - サービスアカウントを確認: `bandq-dx@bandq-dx.iam.gserviceaccount.com`
   - `Secret Manager Secret Accessor`ロールを持っていることを確認

2. **Google管理コンソールにて（スーパー管理者権限が必要）:**
   - セキュリティ > アクセスとデータ制御 > APIコントロールに移動
   - ドメイン全体の委任を管理
   - サービスアカウントのクライアントIDを追加
   - 必要なスコープを追加:
     ```
     https://www.googleapis.com/auth/drive.readonly
     https://www.googleapis.com/auth/documents.readonly
     ```

### 3. **修正版実装のデプロイ**

```bash
# ビルドとデプロイ
gcloud builds submit --tag gcr.io/bandq-dx/meet-minutes-processor
gcloud run deploy gws-meet-notes \
    --image gcr.io/bandq-dx/meet-minutes-processor \
    --platform managed \
    --region asia-northeast1 \
    --service-account=bandq-dx@bandq-dx.iam.gserviceaccount.com \
    --set-env-vars="GCP_PROJECT_ID=bandq-dx" \
    --set-env-vars="SERVICE_ACCOUNT_SECRET_NAME=service-account-key" \
    --set-env-vars="MONITORED_USERS=masuda.g@bandq.jp" \
    --set-env-vars="WEBHOOK_URL=https://gws-meet-notes-816821699190.asia-northeast1.run.app/webhook"
```

### 4. **実装のテスト**

```bash
# 認証テスト
curl -X POST https://gws-meet-notes-816821699190.asia-northeast1.run.app/test-authentication

# フォルダ検出テスト
curl -X POST https://gws-meet-notes-816821699190.asia-northeast1.run.app/test-folder-check

# watchチャネル設定
curl -X POST https://gws-meet-notes-816821699190.asia-northeast1.run.app/renew-all-watches

# ヘルスチェック
curl https://gws-meet-notes-816821699190.asia-northeast1.run.app/health
```

## 🔍 主要な改善点

### 認証フロー
1. **優先順位:**
   - Secret Manager（セキュア）
   - サービスアカウントファイル（開発環境のみ）
   - デフォルト認証情報（非推奨、Secret Manager設定時のフォールバック削除）

2. **検証:**
   - 適切なJSON形式の検証
   - 必要フィールドの確認
   - ドメイン全体委任設定の確認

### フォルダ検出
1. **多言語サポート:**
   - 英語と日本語のフォルダ名
   - 広範囲検索フォールバック
   - Meet関連フォルダのパターンマッチング

2. **エラーハンドリング:**
   - 特定の名前が見つからない場合の適切なフォールバック
   - デバッグ用の包括的なログ出力

### Watch通知
1. **処理の改善:**
   - より良い変更検出ロジック
   - ファイルタイプフィルタリング
   - フォールバック機能

2. **監視:**
   - 詳細なログ出力
   - watchチャネル有効期限の処理
   - エラー分類

## 🛠 設定確認

以下のエンドポイントを使用して設定を確認してください:

- `/health` - システム全体のステータス
- `/test-authentication` - ドメイン全体委任テスト
- `/test-folder-check` - フォルダアクセス確認
- `/renew-all-watches` - watchチャネル設定

## 📋 トラブルシューティング

### Secret Managerがまだ失敗する場合:
1. サービスアカウントが`Secret Manager Secret Accessor`ロールを持っているかチェック
2. シークレット名が正確に`service-account-key`であることを確認
3. シークレット内のJSONが適切にフォーマットされているかチェック

### フォルダが見つからない場合:
1. ユーザーがGoogle Meet録画を持っているかチェック
2. 異なるフォルダ名（英語/日本語）を試す
3. ドメイン全体委任が適切に設定されているかチェック

### watchチャネルが失敗する場合:
1. webhook URLがアクセス可能かチェック
2. ドメイン全体委任のスコープをチェック
3. サービスアカウントがDrive APIアクセス権を持っているか確認

実装は現在堅牢であり、以前に失敗していたすべてのシナリオを処理できるはずです。