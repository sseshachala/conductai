FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev git && rm -rf /var/lib/apt/lists/*
COPY apps/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY apps/api/playbooks ./playbooks
COPY apps/api/prompts ./prompts
COPY apps/api/scripts ./scripts
COPY tools/security-e2e/bootstrap.py tools/security-e2e/serve.py /harness/
ENV PYTHONPATH=/app
