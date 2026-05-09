FROM python:3.12-slim

# Need procps for `pgrep` in HEALTHCHECK below
RUN apt-get update && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

# Run as non-root for safety
RUN groupadd --gid 1000 bot && \
    useradd --uid 1000 --gid bot --create-home bot

WORKDIR /app

# Install deps first (layer cache)
COPY --chown=bot:bot requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source
COPY --chown=bot:bot bot/ ./bot/

# Persistence dir — mount a volume here in compose
RUN mkdir -p /app/state && chown -R bot:bot /app/state

USER bot

# Default state path inside the container
ENV PERSISTENCE_PATH=/app/state/bot.pickle

# Git commit SHA injected at build time. Surfaced via /version. Defaults to
# "dev" so a `docker build` without --build-arg still produces a working image.
ARG GIT_SHA=dev
ENV BOT_GIT_SHA=$GIT_SHA

# Long-poll bot — process liveness is sufficient. Use pgrep against the bot
# entrypoint command line so we don't false-positive on shells or installers.
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
    CMD pgrep -f "python -m bot.main" >/dev/null 2>&1 || exit 1

CMD ["python", "-m", "bot.main"]
