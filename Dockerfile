FROM python:3.6-alpine

RUN apk add -U --no-cache gcc build-base linux-headers ca-certificates python3 python3-dev libffi-dev libressl-dev

COPY requirements.txt /

RUN pip install --no-cache-dir -r /requirements.txt && mkdir /app

COPY launcher-service.py /app
COPY starter.sh /app

WORKDIR /app
CMD ["./starter.sh"]
