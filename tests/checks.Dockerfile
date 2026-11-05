FROM python:3.15.2-slim-trixie
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tests
CMD ["python", "-u", "/tests/smoke.py"]
