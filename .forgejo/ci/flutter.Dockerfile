# CI-Image für den App-Job: Node (für actions/checkout) + Flutter-SDK ohne Android.
# Bauen auf dem Runner-Host: docker build -t familienhub-ci-flutter:3.47.7 -f .forgejo/ci/flutter.Dockerfile .forgejo/ci
FROM node:20-bookworm
ARG FLUTTER_VERSION=3.47.7
RUN apt-get update && apt-get install -y --no-install-recommends git curl unzip xz-utils ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
    | tar -xJ -C /opt \
 && git config --global --add safe.directory '*' \
 && /opt/flutter/bin/flutter config --no-analytics --no-cli-animations \
 && /opt/flutter/bin/flutter precache --no-android --no-ios --no-web --no-linux --no-windows --no-macos --no-fuchsia \
 && /opt/flutter/bin/flutter --version
ENV PATH="/opt/flutter/bin:${PATH}" PUB_CACHE=/opt/pub-cache
