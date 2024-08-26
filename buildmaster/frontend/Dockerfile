FROM docker.io/nginx:alpine

RUN mkdir /var/instances /var/lib/buildmaster-frontend

VOLUME ["/var/instances"]

COPY configs/buildmaster-frontend.conf /etc/nginx/conf.d/default.conf
COPY www/. /var/lib/buildmaster-frontend/
