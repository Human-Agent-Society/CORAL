FROM python:3.12-slim

WORKDIR /workspace

COPY verification/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

COPY verification/evaluator.py /workspace/evaluator.py
COPY references /workspace/references
COPY scripts /workspace/scripts

ENV PYTHONUNBUFFERED=1

CMD ["python", "evaluator.py", "scripts/init.py"]
