#!/usr/bin/env sh

export STATUS_CHECK_INTERVAL=10
export STATUS_CHECK_COUNT=12
export LOG_LEVEL=10 # debug
export JUPYTERHUB_SERVICE_PREFIX="/services/launcher/"
export JUPYTERHUB_URL="http://192.168.0.31:32180"
export JUPYTERHUB_API_PREFIX="/hub/api"
export JUPYTERHUB_API_TOKEN="ad6b8dc16f624b54a5b7d265f0744c98"
export USER_TOKEN_LIFETIME=1800

#python launcher-service.py flask run -h 0.0.0.0 -p 5000
gunicorn -w 2 -b 127.0.0.1:5000 launcher-service:app
