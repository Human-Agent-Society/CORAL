FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY ../requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy verification code
COPY ../*.py /app/verification/

# Copy problem data
COPY ../../references/problem_data.json /app/references/problem_data.json

# Default command: run evaluator
ENTRYPOINT ["python", "/app/verification/evaluator.py"]

