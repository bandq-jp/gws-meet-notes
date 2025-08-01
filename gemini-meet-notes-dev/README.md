# Google Meet 議事録自動処理システム

Google Meetで生成された議事録を自動的に取得・保存するシステムです。DDDアーキテクチャに基づいて設計されています。

## アーキテクチャ

```
Google Meet → 議事録生成 → Google Drive → Push Notifications → Pub/Sub → Cloud Run
```

## 機能

- Google Driveの変更をリアルタイムで監視
- Meet Recordingsフォルダの議事録を自動検知
- 指定したユーザーのファイルのみを処理
- ローカルストレージへの保存

## デプロイ手順

### 1. 事前準備

1. Google Workspaceの管理者権限でドメイン全体の委任を設定
2. サービスアカウントキーファイルを `service-account.json` として配置
3. 以下の環境変数を設定：
   - `TARGET_USER_EMAIL`: 処理対象のユーザーメールアドレス
   - `GOOGLE_CLOUD_PROJECT`: Google CloudプロジェクトID

### 2. Cloud Runへのデプロイ

Cloud Runコンソールで「ソースから継続的にデプロイ」を選択し、このリポジトリを指定してください。

### 3. インフラ設定

デプロイ後、Google Drive Push Notificationsを設定：

## 環境変数

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|------------|------|
| `TARGET_USER_EMAIL` | ✓ | - | 処理対象のユーザー |
| `GOOGLE_CLOUD_PROJECT` | ✓ | - | Google CloudプロジェクトID |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | `/app/service-account.json` | サービスアカウントキーファイルパス |
| `PUBSUB_TOPIC_NAME` | - | `meet-notes-topic` | Pub/Subトピック名 |
| `STORAGE_PATH` | - | `/tmp/recordings` | ローカル保存パス |
| `LOG_LEVEL` | - | `INFO` | ログレベル |

## API エンドポイント

- `POST /`: Pub/Sub通知の処理
- `POST /setup`: インフラ設定
- `GET /health`: ヘルスチェック
- `GET /config`: 設定確認

## ディレクトリ構造

```
src/
├── domain/          # ドメイン層
│   ├── entities/    # エンティティ
│   ├── value_objects/ # 値オブジェクト
│   ├── repositories/ # リポジトリインターフェース
│   └── services/    # ドメインサービス
├── application/     # アプリケーション層
│   ├── use_cases/   # ユースケース
│   ├── services/    # アプリケーションサービス
│   └── dto/         # データ転送オブジェクト
├── infrastructure/ # インフラ層
│   ├── google_apis/ # Google API実装
│   ├── pubsub/      # Pub/Sub実装
│   └── storage/     # ストレージ実装
├── presentation/   # プレゼンテーション層
│   ├── handlers/   # リクエストハンドラー
│   └── middleware/ # ミドルウェア
└── shared/         # 共通コンポーネント
    ├── exceptions/ # 例外クラス
    └── types/      # 型定義
```