FROM docker.io/nginx:alpine

RUN mkdir /var/sources /var/instances /var/lib/buildmaster-frontend

VOLUME ["/var/sources", "/var/instances"]

COPY configs/buildmaster-frontend.conf /etc/nginx/conf.d/default.conf
COPY www/. /var/lib/buildmaster-frontend/
