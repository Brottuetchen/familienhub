# Familienhub – Backend + Web-App in einem Image

# 1) Flutter-Web-App bauen (gleiche Oberfläche wie die Android-App)
#    Lokal mit vorhandenem Flutter-Image bauen: --build-arg FLUTTER_IMAGE=<image>
ARG FLUTTER_IMAGE=ghcr.io/cirruslabs/flutter:stable
FROM ${FLUTTER_IMAGE} AS web
USER root
# Flutter-SDK kann einem anderen Nutzer gehören (z. B. lokales Image) → Git-Prüfung abschalten
RUN git config --global --add safe.directory '*'
WORKDIR /src/app
COPY app/pubspec.yaml app/pubspec.lock ./
RUN flutter pub get
COPY app/ ./
# --no-web-resources-cdn: CanvasKit vom eigenen Server statt von gstatic.com
RUN flutter build web --release --no-web-resources-cdn

# 2) Backend
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies zuerst (Layer-Caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=web /src/app/build/web/ ./public/

WORKDIR /app/backend

# Nicht als root laufen. Feste UID, damit eingebundene Dateien (z. B. Firebase-Dienstkonto) passend
# freigegeben werden können: chown 10001:10001 <datei> auf dem Host.
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin familienhub
USER 10001:10001

EXPOSE 8000

# Healthcheck gegen den API-Health-Endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
