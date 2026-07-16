FROM python:3.11-alpine3.20 AS temp
RUN apk --update --no-cache add npm
RUN npm install -g sass@1.99

WORKDIR /src
COPY . .

RUN npm ci --legacy-peer-deps
ENV NODE_ENV="production"
RUN npm run build
RUN sass scss/main.scss:cubicweb_francearchives/data/css/francearchives.bundle.css
RUN python setup.py sdist

FROM logilab/cubicweb-base:cw4-postgres16-python3.11
USER root
RUN apt update && apt -y --no-install-recommends install \
    screen \
    poppler-utils \
    procps \
    wget \
    && rm -rf /var/lib/apt/lists/*
# XXX restart worker after a number of requests (prevent memory leak)
# TODO remove when https://forge.extranet.logilab.fr/cubicweb/docker-cubicweb/-/issues/8 is fixed
RUN echo "max-requests = 128000" >> /etc/uwsgi/uwsgi.ini
# enable stats socket used by uwsgi prometheus exporter
RUN echo "memory-report = true" >> /etc/uwsgi/uwsgi.ini
RUN echo "stats = 127.0.0.1:8001" >> /etc/uwsgi/uwsgi.ini
USER cubicweb
COPY --from=temp /src/dist/cubicweb-francearchives-*.tar.gz .
COPY ./requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
RUN pip install cubicweb-francearchives-*.tar.gz
RUN pip install pyramid-session-redis
ENV CUBE=francearchives
ENV CW_DB_NAME=${CUBE}
RUN docker-cubicweb-helper create-instance
USER root
RUN rm /requirements.txt
USER cubicweb
