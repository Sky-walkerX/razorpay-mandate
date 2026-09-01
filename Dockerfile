# Stage 1: Build the Vite frontend bundle
FROM node:20-slim AS frontend
WORKDIR /app/web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# Stage 2: Python runtime with Starlette backend
FROM python:3.12-slim
WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python package
COPY pyproject.toml ./
COPY src/ ./src
RUN pip install --no-cache-dir .

# Copy corpus, policies, keys, and conformance results
COPY corpus/ ./corpus
COPY policies/ ./policies
COPY results/ ./results
COPY results-conformance/ ./results-conformance
COPY revocations.jsonl ./revocations.jsonl

# The issuer keypair is named file by file, never `COPY .mandate/`. The gateway
# verifies tokens and must hold the public key only; an image carrying
# issuer_private.key could mint itself a higher cap, which is the whole property
# the offline issuer exists to provide.
COPY .mandate/token_pool.json ./.mandate/token_pool.json
COPY .mandate/keys/issuer_public.key ./.mandate/keys/issuer_public.key

# Copy built frontend assets from Stage 1
COPY --from=frontend /app/web/dist ./web/dist

# Default environment configuration
ENV PORT=8080
ENV HOST=0.0.0.0
ENV MANDATE_LLM_PROVIDER=vertex
ENV GEMINI_VERTEX_LOCATION=global

EXPOSE 8080

CMD ["sh", "-c", "mandate serve --host 0.0.0.0 --port ${PORT:-8080} --static-dir web/dist"]
