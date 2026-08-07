FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=realtyos.settings

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    fonts-dejavu-core \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system nexora \
    && adduser --system --ingroup nexora nexora \
    && mkdir -p /app/media /app/staticfiles \
    && chmod +x entrypoint.sh \
    && chown -R nexora:nexora /app

USER nexora

CMD ["./entrypoint.sh"]
