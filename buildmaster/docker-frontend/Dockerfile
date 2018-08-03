FROM nginx:alpine

RUN mkdir /var/sources /var/instances

VOLUME ["/var/sources", "/var/instances"]

COPY buildmaster-frontend.conf /etc/nginx/conf.d/default.conf
