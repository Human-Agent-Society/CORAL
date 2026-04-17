FROM python:3.12-slim

# System deps: git, Node.js (for codex CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Codex CLI
RUN npm install -g @openai/codex

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
# afterwards, so we re-inject both the CORAL venv and the per-agent
# VIRTUAL_ENV here.
RUN printf '#!/bin/sh\n\
if [ -n "$VIRTUAL_ENV" ] && [ -d "$VIRTUAL_ENV/bin" ]; then\n\
    PATH="$VIRTUAL_ENV/bin:$PATH"\n\
fi\n\
if [ -d /app/.venv/bin ]; then\n\
    PATH="/app/.venv/bin:$PATH"\n\
fi\n' > /etc/profile.d/coral-venv.sh && chmod +x /etc/profile.d/coral-venv.sh

ENV CORAL_IN_DOCKER=1
COPY docker/codex/entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
