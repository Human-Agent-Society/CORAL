# EngDesign

The tasks in this directory are all from [EngDesign](https://github.com/AGI4Engineering/EngDesign/tree/main). We have selected tasks from this project that are relatively complex and close to engineering practice.

```
`CY_03`
`WJ_01`
`XY_05`
`AM_02`
`AM_03`
`YJ_02`
`YJ_03`

```

## Environment
### 1. Install and Log in to Docker

- Register at [hub.docker.com](https://hub.docker.com/) and **verify your email**.
- Download and install Docker Desktop on your machine: [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Launch Docker Desktop and log in to your account.
- Make sure Docker Desktop has access to your drive (check settings).

### 2. Authenticate via CLI

In a terminal, run:

   ```bash
   docker login -u your_dockerhub_username
   ```

### 3. Build the Docker Image

Run the following command in the root directory of this project:

   ```bash
   docker build -t engdesign-sim .
   ```

### 4. Start a Docker Container

Mount your local project directory and start a bash session in the container:

   ```bash
   docker run -it --rm -v /path/to/your/local/directory:/app --entrypoint bash engdesign-sim
   ```

## Evaluation
```
export ENGDESIGN_EVAL_MODE=docker
export ENGDESIGN_DOCKER_IMAGE=engdesign-sim
python -m frontier_eval task=engdesign algorithm=openevolve algorithm.iterations=10
```