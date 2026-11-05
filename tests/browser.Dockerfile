FROM mcr.microsoft.com/playwright/python:v1.56.0-noble
RUN pip install --disable-pip-version-check --no-cache-dir playwright==1.56.0
WORKDIR /tests
COPY browser.py /tests/browser.py
CMD ["python", "-u", "/tests/browser.py"]
