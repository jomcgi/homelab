FROM cgr.dev/chainguard/python:latest-dev as builder

ENV LANG=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/mesop_app/venv/bin:$PATH"
WORKDIR /mesop_app

USER root

RUN python -m venv /venv
RUN pip install mesop pandas gunicorn
# RUN groupadd -g 900 mesop && useradd -u 900 -s /bin/bash -g mesop mesop
FROM cgr.dev/chainguard/python:latest

WORKDIR /mesop_app

ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

WORKDIR /mesop_app
# Create non-root user

USER mesop

# Add app code here
COPY app/. /.


# Run Mesop through gunicorn. Should be available at localhost:9090
CMD ["gunicorn", "--bind", "0.0.0.0:9090", "main:me"]