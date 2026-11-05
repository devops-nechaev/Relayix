FROM python:3.13-alpine
RUN apk add --no-cache postgresql-client
WORKDIR /tests
CMD ["python", "-u", "/tests/smoke.py"]
