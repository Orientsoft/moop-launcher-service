FROM python:3.6-alpine as base

FROM base as builder
RUN apk add --no-cache gcc musl-dev

RUN mkdir /install && mkdir /app
WORKDIR /install
COPY requirements.txt /requirements.txt
RUN pip install --install-option="--prefix=/install" -r /requirements.txt 

FROM base
COPY --from=builder /install /usr/local

RUN mkdir /install && mkdir /app
WORKDIR /app
COPY launcher-service.py /app
COPY starter.sh /app

CMD ["./starter.sh"]
