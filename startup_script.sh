#!/usr/bin/env bash

declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /container.env
chmod 0644 /etc/cron.d/transgene-ext-cron
touch /var/log/transgene_ext_pipeline.log
crontab /etc/cron.d/transgene-ext-cron
cron

tail -f /dev/null