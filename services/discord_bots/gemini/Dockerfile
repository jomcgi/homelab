FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /bot
COPY /services/discord_bots/gemini/requirements.txt .

USER root

RUN wget https://astral.sh/uv/install.sh && source install.sh && rm install.sh
RUN /root/.cargo/bin/uv venv /bot/venv
RUN /root/.cargo/bin/uv pip install --no-cache --python /bot/venv -r requirements.txt
RUN mkdir -p /services/discord_bots/gemini && mkdir /services/discord_bots/shared && touch /services/__init__.py && touch /services/discord_bots/__init__.py

FROM cgr.dev/chainguard/python:latest

WORKDIR /bot

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH="/:/bot"

COPY --from=builder /bot/. .

COPY services/discord_bots/shared /services/discord_bots/shared
COPY services/discord_bots/gemini /services/discord_bots/gemini


ENTRYPOINT ["/bot/venv/bin/python", "/services/discord_bots/gemini/main.py"]