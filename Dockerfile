FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; bs4 is pure-python, no build tools needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DATA_DIR=/tmp/mena-agent

EXPOSE 8080

# Cloud Run sets $PORT; the CLI reads it via os.getenv in cli.py.
CMD ["python", "main.py", "serve"]
