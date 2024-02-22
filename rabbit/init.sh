#!/bin/sh


( rabbitmqctl wait --timeout 60 "$RABBITMQ_PID_FILE" ; \
rabbitmqctl add_vhost destiny_bot ;) &

( rabbitmqctl wait --timeout 60 "$RABBITMQ_PID_FILE" ; \
rabbitmqctl add_user bot "$RABBIT_BOT_PASS" 2>/dev/null ; \
rabbitmqctl set_user_tags bot administrator ; \
rabbitmqctl set_permissions -p destiny_bot bot  ".*" ".*" ".*" ;) &

( rabbitmqctl wait --timeout 60 "$RABBITMQ_PID_FILE" ; \
rabbitmqctl add_user site "$RABBIT_SITE_PASS" 2>/dev/null ; \
rabbitmqctl set_user_tags site administrator ; \
rabbitmqctl set_permissions -p destiny_bot site  ".*" ".*" ".*" ;) &

# shellcheck disable=SC2068
rabbitmq-server $@