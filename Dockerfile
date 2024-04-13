FROM python:3.11-alpine

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
COPY email2signal ./email2signal
RUN touch README.md

RUN poetry install

ENV SIGNAL_REST_URL \
    SENDER_NUMBER \
    SMTP_HOST \
    SMTP_USER \
    SMTP_PASSWORD \
    SMTP_PORT=587

EXPOSE 8025
ENTRYPOINT ["poetry", "run", "python", "-m", "email2signal.app"]
