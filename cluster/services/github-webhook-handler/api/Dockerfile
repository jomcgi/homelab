FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /api
COPY requirements.txt .

# USER root

RUN wget https://astral.sh/uv/install.sh && \
    sh install.sh && \
    rm install.sh && \
    source $HOME/.local/bin/env

RUN uv venv /api/venv
RUN uv pip install --no-cache --python /api/venv -r requirements.txt

FROM cgr.dev/chainguard/python:latest

WORKDIR /api

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

COPY --from=builder /api/venv /venv
COPY . .

ENTRYPOINT ["python", "-m", "fastapi", "run", "main.py", "--port", "9090"]