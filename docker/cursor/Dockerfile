FROM python:3.12-slim

# System deps: git + curl (curl is used to fetch the cursor-agent installer
# script per https://cursor.com/docs/cli/overview).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install cursor-agent CLI. The official installer drops the binary at
# ~/.local/bin/cursor-agent (i.e. /root/.local/bin in this image).
RUN curl -fsSL https://cursor.com/install | bash
ENV PATH="/root/.local/bin:$PATH"

# Install CORAL
WORKDIR /app
COPY pyproject.toml uv.lock* README* ./
COPY coral/ coral/
RUN sed -i \
        -e 's/"hatchling", "hatch-vcs"/"hatchling"/' \
        -e 's/dynamic = \["version"\]/version = "0.3.1"/' \
        -e '/^\[tool\.hatch\.version\]$/,+1d' \
        -e '/^\[tool\.hatch\.build\.hooks\.vcs\]$/,+1d' \
        pyproject.toml
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Ensure agent venvs survive login-shell PATH resets (/etc/profile on
# Debian sets PATH absolutely).  /etc/profile sources /etc/profile.d/*.sh
# afterwards, so we re-inject both the CORAL venv, the per-agent
# VIRTUAL_ENV, and the cursor-agent install dir here.
RUN printf '#!/bin/sh\n\
if [ -n "$VIRTUAL_ENV" ] && [ -d "$VIRTUAL_ENV/bin" ]; then\n\
    PATH="$VIRTUAL_ENV/bin:$PATH"\n\
fi\n\
if [ -d /app/.venv/bin ]; then\n\
    PATH="/app/.venv/bin:$PATH"\n\
fi\n\
if [ -d /root/.local/bin ]; then\n\
    PATH="/root/.local/bin:$PATH"\n\
fi\n' > /etc/profile.d/coral-venv.sh && chmod +x /etc/profile.d/coral-venv.sh

ENV CORAL_IN_DOCKER=1
COPY docker/cursor/entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
