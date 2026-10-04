FROM python:3.11-slim

WORKDIR /app

# Системные зависимости: Pillow + шрифты для watermark
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Убедимся, что папки для uploads/protected существуют
RUN mkdir -p /app/uploads /app/protected

# Render подставляет $PORT автоматически; fallback 8000 для локального запуска
CMD ["sh", "-c", "uvicorn src.main:auth_app --host 0.0.0.0 --port ${PORT:-8000}"]
