FROM docker.io/nginx:alpine

RUN mkdir /var/buildmaster /var/lib/buildmaster-frontend

VOLUME ["/var/buildmaster"]

COPY configs/buildmaster-frontend.conf /etc/nginx/conf.d/default.conf
COPY www/. /var/lib/buildmaster-frontend/
