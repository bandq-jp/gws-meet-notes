# Dockerfile
# Cloud Runにデプロイするためのセキュアなコンテナイメージを定義

# セキュアで軽量なベースイメージを使用
FROM python:3.11-slim

# セキュリティ向上のため非rootユーザーを作成
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# システムの更新とセキュリティパッチ適用
RUN apt-get update && apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 環境変数を設定
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# アプリケーションの作業ディレクトリを作成
WORKDIR /app

# 依存関係ファイルをコピー（レイヤーキャッシュ最適化）
COPY requirements.txt .

# pipをアップグレードし、依存関係をセキュアにインストール
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY --chown=appuser:appgroup . .

# 非rootユーザーに切り替え
USER appuser

# ヘルスチェック設定
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# セキュアなuvicornサーバーを実行
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--access-log", "--log-level", "info"]