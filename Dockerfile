FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (git and curl)
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application modules, static assets, manifests, and example fixtures
COPY sequenceproof.py server.py index.html repository_runner.py runner_contract.py core.py jobs.py ./
COPY sandbox/ sandbox/
COPY static/ static/
COPY .sequenceproof/ .sequenceproof/
COPY examples/ examples/

ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
