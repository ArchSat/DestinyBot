FROM ubuntu:latest
LABEL authors="archsat"

FROM rabbitmq:3.10.7-management

ADD init.sh /init.sh
RUN chmod +x /init.sh

CMD ["/init.sh"]