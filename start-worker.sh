#! /bin/sh
celery -A launcher-worker worker --concurrency=2 --loglevel=info