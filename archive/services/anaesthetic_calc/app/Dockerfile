FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .

USER root

RUN wget https://astral.sh/uv/install.sh && source install.sh && rm install.sh
RUN /root/.cargo/bin/uv venv /app/venv
RUN /root/.cargo/bin/uv pip install --no-cache --python /app/venv -r requirements.txt

FROM cgr.dev/chainguard/python:latest

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

COPY . .
COPY --from=builder /app/venv /venv

ENTRYPOINT ["python"]
CMD ["-m", "gunicorn", "--bind", "0.0.0.0:9090", "main:me"]