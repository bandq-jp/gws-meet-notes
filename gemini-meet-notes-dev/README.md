# Google Meet Minutes Processor - 完全なセキュアソリューション

Google Meet RecordingsフォルダのGoogleドキュメント追加を監視し、リアルタイムで処理するセキュアなCloud Runアプリケーションです。

## 🔥 主要な改善点

### 1. **セキュリティの大幅向上**
- ✅ サービスアカウントキーファイルの完全削除
- ✅ Secret Manager による安全なキー管理
- ✅ Google-managed keys を使用したドメイン全体の委任
- ✅ 非rootユーザーでのコンテナ実行
- ✅ セキュアなログ出力（機密情報の除外）

### 2. **認証方式の最適化**
- ✅ Secret Manager からのサービスアカウントキー取得
- ✅ ドメイン全体の委任の正しい実装
- ✅ エラーハンドリングの改善
- ✅ 複数の認証方式のフォールバック対応

### 3. **Push Notification の改善**
- ✅ Webhook のセキュリティ検証
- ✅ エラーの分類とリトライ戦略
- ✅ 構造化されたログ出力
- ✅ フォールバック処理の実装

### 4. **運用面の向上**
- ✅ ヘルスチェックエンドポイント
- ✅ 認証テスト機能
- ✅ 詳細な監視とログ出力
- ✅ Dockerコンテナの最適化

## 🚀 クイックスタート

### 1. 環境変数の設定

```bash
# 必須設定
export GCP_PROJECT_ID="your-project-id"
export WEBHOOK_URL="https://your-cloud-run-url/webhook"
export MONITORED_USERS="user1@example.com:folder_id1,user2@example.com"

# 認証方式1: Secret Manager（推奨）
export SERVICE_ACCOUNT_SECRET_NAME="service-account-key"

# 認証方式2: Google-managed keys（最もセキュア）
export DELEGATION_SERVICE_ACCOUNT_EMAIL="delegation@your-project.iam.gserviceaccount.com"

# 認証方式3: ローカルファイル（開発用のみ）
export SERVICE_ACCOUNT_FILE_PATH="/path/to/service-account.json"
```

### 2. Google Cloud での設定

#### サービスアカウントの作成と設定
```bash
# 1. サービスアカウントを作成
gcloud iam service-accounts create meet-minutes-processor \
    --display-name="Meet Minutes Processor"

# 2. 必要な権限を付与
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
    --member="serviceAccount:meet-minutes-processor@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# 3. ドメイン全体の委任を有効化（Google Admin Consoleで設定）
```

#### Secret Manager にキーを保存
```bash
# サービスアカウントキーを Secret Manager に保存
gcloud secrets create service-account-key \
    --data-file=path/to/your-service-account-key.json
```

### 3. Cloud Run へのデプロイ

```bash
# 1. コンテナイメージをビルド
gcloud builds submit --tag gcr.io/$GCP_PROJECT_ID/meet-minutes-processor

# 2. Cloud Run にデプロイ
gcloud run deploy meet-minutes-processor \
    --image gcr.io/$GCP_PROJECT_ID/meet-minutes-processor \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID" \
    --set-env-vars="SERVICE_ACCOUNT_SECRET_NAME=service-account-key" \
    --set-env-vars="MONITORED_USERS=$MONITORED_USERS" \
    --service-account="meet-minutes-processor@$GCP_PROJECT_ID.iam.gserviceaccount.com"
```

## 🔧 API エンドポイント

### ヘルスチェック
```bash
GET /health
```
- アプリケーションの状態確認
- 設定の妥当性チェック
- 認証設定の確認

### 認証テスト
```bash
POST /test-authentication
```
- 認証設定の動作確認
- ドメイン全体の委任のテスト

### フォルダーチェックテスト
```bash
POST /test-folder-check
```
- Meet Recordingsフォルダへのアクセステスト
- 権限の確認

### Watch チャネルの更新
```bash
POST /renew-all-watches
```
- 全ユーザーの監視チャネルを更新
- Cloud Scheduler から定期実行推奨

### Webhook エンドポイント
```bash
POST /webhook
```
- Google Drive からの通知を受信
- 自動的にドキュメントを処理

## 🔐 セキュリティベストプラクティス

### 1. **認証方式の選択**

**推奨順位:**
1. **Google-managed keys** (最もセキュア)
2. **Secret Manager** (推奨)
3. **ローカルファイル** (開発用のみ)

### 2. **環境変数の管理**
```bash
# 本番環境では Cloud Run の環境変数設定を使用
gcloud run services update meet-minutes-processor \
    --set-env-vars="SECRET_KEY=value" \
    --region=asia-northeast1
```

### 3. **IAM 権限の最小化**
- 必要最小限の権限のみを付与
- 定期的な権限の見直し
- サービスアカウントの分離

## 📊 監視とログ

### Cloud Logging での監視
```bash
# アプリケーションログの確認
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=meet-minutes-processor"

# エラーログのフィルタリング
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR"
```

### メトリクス監視
- Cloud Monitoring でのメトリクス設定
- アラートポリシーの設定
- SLO/SLI の定義

## 🔄 トラブルシューティング

### よくある問題と解決法

#### 1. **Secret Manager エラー**
```
Error: does not match the expected format [projects/*/secrets/*/versions/*]
```
**解決法:** 環境変数 `SERVICE_ACCOUNT_SECRET_NAME` にシークレット名のみを設定（パス形式ではない）

#### 2. **ドメイン全体の委任エラー**
```
Error: Domain-wide delegation not available with Cloud Run default credentials
```
**解決法:** Secret Manager または Google-managed keys を使用

#### 3. **Meet Recordings フォルダが見つからない**
```
Error: 'Meet Recordings' folder not found
```
**解決法:** 
- ユーザーのGoogle Driveにフォルダが存在することを確認
- サービスアカウントに適切な権限が付与されていることを確認

#### 4. **Webhook が受信されない**
**解決法:**
- Cloud Run の URL が正しく設定されていることを確認
- `/webhook` エンドポイントへのルーティング確認
- Google Drive API の Push Notification 設定確認

## 📋 デプロイメントチェックリスト

- [ ] サービスアカウントの作成と権限設定
- [ ] Google Admin Console でのドメイン全体の委任設定
- [ ] Secret Manager への認証キー保存
- [ ] 環境変数の設定
- [ ] Cloud Run へのデプロイ
- [ ] ヘルスチェックエンドポイントの確認
- [ ] 認証テストの実行
- [ ] Watch チャネルの設定
- [ ] テスト用ドキュメントでの動作確認
- [ ] ログ監視の設定
- [ ] アラートポリシーの設定

## 🛠 カスタマイズ

### ドキュメント処理のカスタマイズ
`_process_document_content()` 関数を編集して、以下の機能を追加できます：

- Firestore への保存
- AI による要約生成
- Slack/Teams への通知
- 外部 API への転送

### 監視対象の拡張
`MONITORED_USERS` 環境変数を編集して、監視対象ユーザーを追加・削除できます。

## 📞 サポート

問題が発生した場合は、以下の順序で確認してください：

1. **ヘルスチェック**: `/health` エンドポイントでアプリケーションの状態確認
2. **認証テスト**: `/test-authentication` で認証設定の確認
3. **ログ確認**: Cloud Logging でエラーログの確認
4. **権限確認**: IAM 設定の見直し
5. **Google Admin Console**: ドメイン全体の委任設定の確認

---

このソリューションにより、セキュアで安定した Google Meet 議事録処理システムを構築できます。