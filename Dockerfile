FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        wget \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip

RUN pip install -r requirements.txt \
    && pip check

COPY . .

ARG APP_VERSION
ARG BUILD_DATE
ARG VCS_REF
ENV APP_VERSION=$APP_VERSION
ENV BUILD_DATE=$BUILD_DATE
ENV VCS_REF=$VCS_REF
RUN printf '%s\n' "$BUILD_DATE" > /app/.build-date

RUN mkdir -p /app/content /app/downloads /app/logs

CMD ["python", "main.py", "--env", "prod"]
