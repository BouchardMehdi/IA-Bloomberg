FROM postgres:16-alpine
RUN apk add --no-cache age
COPY backup.sh restore-check.sh /opt/backup/
RUN chmod 755 /opt/backup/*.sh
ENTRYPOINT ["/bin/sh", "/opt/backup/backup.sh"]
