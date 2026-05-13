FROM python:3.11-slim

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

COPY evaluator.py /workspace/evaluator.py

ENV PYTHONUNBUFFERED=1

# Expects submission.json to be mounted at /workspace/submission.json
CMD ["python", "evaluator.py", "--submission", "/workspace/submission.json"]
