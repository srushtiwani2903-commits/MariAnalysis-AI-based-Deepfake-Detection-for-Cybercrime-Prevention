# MariAnalysis - backend runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Core runtime deps (heuristic mode + API work with these only).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# AI/model deps are optional; install via a build arg to keep image lean:
#   docker build --build-arg INSTALL_AI_DEPS=1 .
ARG INSTALL_AI_DEPS=0
COPY requirements-ai.txt .
RUN if [ "$INSTALL_AI_DEPS" = "1" ]; then \
        pip install --no-cache-dir -r requirements-ai.txt; \
    fi

COPY . .

RUN mkdir -p uploads reports security/logs

EXPOSE 5001

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5001", "--timeout", "120", "app:app"]
