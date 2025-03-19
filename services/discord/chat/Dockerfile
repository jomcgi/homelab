FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /bot
COPY /services/discord/chat/requirements.txt .

USER root

# RUN wget https://astral.sh/uv/install.sh && source install.sh && rm install.sh
# RUN /root/.cargo/bin/uv venv /bot/venv
# RUN /root/.cargo/bin/uv pip install --no-cache --python /bot/venv -r requirements.txt
RUN pip install uv && \
    python3 -m uv venv /bot/venv && \
    python3 -m uv pip install --no-cache --python /bot/venv -r requirements.txt
RUN mkdir -p /services/discord/chat/ && \
    mkdir /services/discord/shared && \
    touch /services/__init__.py && \
    touch /services/discord/__init__.py

FROM cgr.dev/chainguard/python:latest

WORKDIR /bot

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH="/:/bot"

COPY --from=builder /bot/. .

COPY services/discord/shared /services/discord/shared
COPY services/discord/chat /services/discord/chat


ENTRYPOINT ["/bot/venv/bin/python", "/services/discord/chat/main.py"]