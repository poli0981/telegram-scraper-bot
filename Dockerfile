FROM python:3.12-slim

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

# No HEALTHCHECK — bot is long-poll, "alive" == "process running"
CMD ["python", "-m", "bot.main"]
