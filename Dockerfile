FROM python:3.6-alpine

RUN apk update \
  && apk add --virtual build-deps gcc python3-dev musl-dev \
  && apk add postgresql-dev=9.6.13-r0 --repository=http://dl-cdn.alpinelinux.org/alpine/v3.6/main \
  && pip install psycopg2-binary==2.8.5

ADD . /app
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "app.py", "--db-host=db"]
