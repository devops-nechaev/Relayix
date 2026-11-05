FROM python:3.16.0a1-slim-trixie
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && pip install --disable-pip-version-check --no-cache-dir playwright==1.64.1 \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tests
COPY browser.py /tests/browser.py
CMD ["python", "-u", "/tests/browser.py"]
