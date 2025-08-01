# 🚨 緊急修正: Cloud Run環境変数エラー

## 問題の原因

**Cloud Run の環境変数 `SERVICE_ACCOUNT_SECRET_NAME` にJSONデータが設定されている**

現在のログから判明した問題:
```
SERVICE_ACCOUNT_SECRET_NAME={"type":"service_account",...}
```

これは **シークレット名** であるべきなのに、**サービスアカウントキーのJSONデータ** が設定されてしまっています。

## 即座に実行すべき修正コマンド

```bash
# 現在のCloud Run設定を確認
gcloud run services describe gws-meet-notes --region=asia-northeast1 --format="value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)"

# 正しい環境変数を設定
gcloud run services update gws-meet-notes \
    --region=asia-northeast1 \
    --set-env-vars="SERVICE_ACCOUNT_SECRET_NAME=service-account-key"

# 他の環境変数も再設定（念のため）
gcloud run services update gws-meet-notes \
    --region=asia-northeast1 \
    --set-env-vars="GCP_PROJECT_ID=bandq-dx" \
    --set-env-vars="MONITORED_USERS=masuda.g@bandq.jp" \
    --set-env-vars="WEBHOOK_URL=https://gws-meet-notes-816821699190.asia-northeast1.run.app/webhook"
```

## 修正後の確認手順

1. **環境変数の確認**
```bash
curl https://gws-meet-notes-816821699190.asia-northeast1.run.app/health
```

2. **認証テスト**
```bash
curl -X POST https://gws-meet-notes-816821699190.asia-northeast1.run.app/test-authentication
```

3. **Watch設定テスト**
```bash
curl -X POST https://gws-meet-notes-816821699190.asia-northeast1.run.app/renew-all-watches
```

## 期待される結果

修正後のログでは以下のようになるはずです:
```
2025-08-01 XX:XX:XX - main - INFO - Accessing Secret Manager with secret name: 'service-account-key'
2025-08-01 XX:XX:XX - main - INFO - Secret Manager path: projects/bandq-dx/secrets/service-account-key/versions/latest
2025-08-01 XX:XX:XX - main - INFO - Successfully retrieved secret from Secret Manager
```

## 根本原因

Cloud Runデプロイ時に環境変数設定でJSONデータがエスケープされずに直接設定されてしまった可能性があります。

### 今後の予防策

1. **YAML設定ファイルを使用**
2. **環境変数の値を個別に設定**
3. **デプロイ後のヘルスチェック確認**

この修正により、Secret Manager認証が正常に動作するようになります。