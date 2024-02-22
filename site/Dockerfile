FROM python:alpine
LABEL authors="archsat"

RUN apk --no-cache add gcc musl-dev libffi-dev openssl-dev python3-dev

WORKDIR /app/

COPY requirements.txt /app/

RUN pip install -r requirements.txt

ADD . /app/
