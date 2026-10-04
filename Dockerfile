FROM python:3.11-slim

WORKDIR /app

# Системные зависимости: Pillow + шрифты для watermark + git для публикации загрузок
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    fonts-dejavu \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Не ждать интерактивного ввода токена: неверный/отсутствующий токен должен падать сразу
ENV GIT_TERMINAL_PROMPT=0

# Защита от "dubious ownership" при работе от имени не-root
RUN git config --system --add safe.directory /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект, включая .git, uploads/ и protected/
# (эти папки больше не исключены в .dockerignore — они «вшиваются» в образ)
COPY . .

# Убедимся, что папки для uploads/protected существуют
RUN mkdir -p /app/uploads /app/protected

# Render подставляет $PORT автоматически; fallback 8000 для локального запуска
CMD ["sh", "-c", "uvicorn src.main:auth_app --host 0.0.0.0 --port ${PORT:-8000}"]
