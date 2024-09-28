FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/mesop_app/venv/bin:$PATH"

WORKDIR /mesop_app
USER root

RUN python -m venv /venv
RUN pip install mesop pandas gunicorn


FROM cgr.dev/chainguard/python:latest

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

WORKDIR /mesop_app
USER mesop

COPY app/. /.
CMD ["gunicorn", "--bind", "0.0.0.0:9090", "main:me"]