# =============================================================================
# YU AI Manager - Multi-stage Dockerfile
# Stage 1: TypeScript build (node:20-alpine)
# Stage 2: Python dependencies (python:3.11-slim)
# Stage 3: Runtime (python:3.11-slim, tini, non-root)
#
# Build examples:
#   docker build -t yu-ai-manager .
#   docker build --build-arg VARIANT=hailo -t yu-ai-manager:hailo .
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: ts-builder — TypeScript bundle build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS ts-builder

WORKDIR /build

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Install dependencies first (cache optimization)
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod=false

# Copy source and build
COPY src/ts/ src/ts/
COPY build.mjs tsconfig.json ./
ENV NODE_ENV=production
RUN pnpm run build

# ---------------------------------------------------------------------------
# Stage 2: python-deps — Pre-install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS python-deps

ARG VARIANT=standard
ARG TARGETARCH

WORKDIR /build

# Add gcc/g++ only for arm64 (needed for onnxruntime source build)
RUN if [ "$TARGETARCH" = "arm64" ]; then \
      apt-get update && apt-get install -y --no-install-recommends gcc g++ \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Hailo variant: install additional wheels
COPY docker/hailo_wheel/ /tmp/hailo_wheel/
RUN if [ "$VARIANT" = "hailo" ] && ls /tmp/hailo_wheel/*.whl 1>/dev/null 2>&1; then \
      pip install --no-cache-dir --prefix=/install /tmp/hailo_wheel/*.whl; \
    fi

# ---------------------------------------------------------------------------
# Stage 3: runtime — Final image
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# tini for PID 1 handling + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
      tini curl sqlite3 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy Python packages from Stage 2
COPY --from=python-deps /install /usr/local

# Copy TS build artifacts from Stage 1
COPY --from=ts-builder /build/static/dist/ static/dist/

# Application source (explicitly listed; avoid COPY . .)
COPY web_ui.py ai_analysis.py db_health.py debug_check.py \
     metadata_extractor.py metadata_extractor_formats.py \
     metadata_extractor_formats_novelai.py \
     metadata_extractor_formats_sd_comfy.py \
     metadata_extractor_formats_stealth.py \
     metadata_extractor_models.py \
     tagdb_tool.py \
     requirements.txt VERSION \
     ./
COPY core/ core/
COPY routes/ routes/
COPY cli/ cli/
COPY extensions/ extensions/
COPY templates/ templates/
COPY mcp_server/ mcp_server/
COPY static/css/ static/css/
COPY static/i18n/ static/i18n/
COPY static/vendor/ static/vendor/
COPY static/favicon.svg static/favicon.svg
COPY profiles/ profiles/

# Data and uploads directories (for volume mounting)
RUN mkdir -p /app/data /app/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["python", "web_ui.py", "--db", "/app/data/tags.db", "--host", "0.0.0.0"]
