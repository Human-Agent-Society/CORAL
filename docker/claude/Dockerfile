FROM python:3.12-slim

# System deps: git, Node.js (for claude CLI), and build essentials
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

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Install CORAL
WORKDIR /app
COPY pyproject.toml uv.lock* README* ./
COPY coral/ coral/
RUN uv sync --no-dev

# Entrypoint copies mounted credentials into a writable ~/.claude,
# then runs coral. Host's ~/.claude is mounted at /claude-config (ro).
ENV CORAL_IN_DOCKER=1
COPY docker/claude/entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
