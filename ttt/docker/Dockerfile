# Build on top of a SLIME base image which already includes:
# SGLang, Megatron-LM, flash-attn, TransformerEngine, apex, DeepEP, Ray, uv, etc.
#
# Build from the CORAL repo root:
#   docker build -t coral-ttt -f ttt/docker/Dockerfile .
#
# Override the base image:
#   docker build --build-arg BASE_IMAGE=slimerl/slime:latest -t coral-ttt -f ttt/docker/Dockerfile .
#
# Run (requires --ulimit nofile for Ray):
#   docker run --gpus all --ipc=host --network host \
#     --ulimit memlock=-1 --ulimit stack=67108864 --ulimit nofile=1048576:1048576 \
#     -e CORAL_TASK_YAML=/app/examples/circle_packing/task.yaml \
#     -e HF_CKPT=/path/to/model \
#     coral-ttt:latest

ARG BASE_IMAGE=slimerl/slime:latest

FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV UV_BREAK_SYSTEM_PACKAGES=1

# =========================
# Install vanilla Megatron-LM
# =========================
ARG MEGATRON_COMMIT=3714d81d418c9f1bca4594fc35f9e8289f652862
RUN pip install pybind11 setuptools wheel
RUN git clone https://github.com/NVIDIA/Megatron-LM.git /opt/megatron-lm && \
    cd /opt/megatron-lm && git checkout ${MEGATRON_COMMIT} && \
    pip install -e . --no-deps --no-build-isolation
ENV MEGATRON_ROOT=/opt/megatron-lm

# =========================
# Install Node.js and opencode (agent runtime)
# =========================
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g opencode-ai@latest

# =========================
# Install SLIME and CORAL into system Python
# =========================
WORKDIR /app

COPY ttt/slime/ ttt/slime/
RUN cd ttt/slime && pip install -e . --no-deps --no-build-isolation

COPY pyproject.toml README* ./
COPY coral/ coral/
COPY ttt/ ttt/
# hatch-vcs reads version from git tags, but .git isn't copied into the image.
# Patch pyproject.toml to use a static version for the Docker build.
RUN sed -i 's|dynamic = \["version"\]|version = "0.1.0"|' pyproject.toml \
    && sed -i '/\[tool.hatch.version\]/,/^$/d' pyproject.toml \
    && sed -i '/\[tool.hatch.build.hooks.vcs\]/,/^$/d' pyproject.toml \
    && sed -i 's|"hatch-vcs",||' pyproject.toml || true
RUN pip install hatchling editables \
    && pip install -e . --no-deps --no-build-isolation \
    && pip install httpx fastapi uvicorn pylatexenc "litellm[proxy]" accelerate peft

# =========================
# Entrypoint
# =========================
ENV CORAL_IN_DOCKER=1
# PYTHONPATH must be set globally so Ray workers inherit it
ENV PYTHONPATH="/app/ttt:/app/ttt/slime:/opt/megatron-lm"
COPY ttt/docker/entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
