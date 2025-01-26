FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /api
COPY services/discord/banter_bank/api/requirements.txt .

USER root
RUN mkdir -p services/discord/banter_bank/ && \
    mkdir services/discord/banter_bank/api && \
    mkdir services/discord/shared && \
    touch services/discord/banter_bank/__init__.py && \
    touch services/discord/__init__.py && \
    touch services/__init__.py


RUN wget https://astral.sh/uv/install.sh && source install.sh && rm install.sh
RUN /root/.cargo/bin/uv venv /api/venv
RUN /root/.cargo/bin/uv pip install --no-cache --python /api/venv -r requirements.txt

FROM cgr.dev/chainguard/python:latest-dev

WORKDIR /api

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH="/:/api"

COPY --from=builder /api/. .

COPY services/discord/banter_bank/models.py services/discord/banter_bank
COPY services/discord/banter_bank/api services/discord/banter_bank/api
COPY services/discord/shared services/discord/shared


ENTRYPOINT ["venv/bin/python", "-m", "fastapi", "run", "services/discord/banter_bank/api/main.py", "--port", "9090"]
