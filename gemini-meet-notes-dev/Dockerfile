# Dockerfile
# Cloud Runにデプロイするためのコンテナイメージを定義

# ベースイメージとして公式のPythonイメージを使用
FROM python:3.11-slim

# 環境変数 PORT を設定。Cloud Runはこのポートにリクエストを送信する
ENV PORT 8080
# Pythonの出力をバッファリングしないように設定
ENV PYTHONUNBUFFERED TRUE

# アプリケーションの作業ディレクトリを作成
WORKDIR /app

# 依存関係ファイルをコピー
COPY requirements.txt .

# pipをアップグレードし、依存関係をインストール
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . .

# コンテナ起動時にuvicornサーバーを実行するコマンド
# 0.0.0.0 にバインドして、コンテナ外部からのリクエストを受け付ける
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]