# Gunicorn configuration for Render deployment
# Optimized for Aiven Free Tier (50 connections max)
# Supports 200-500 users with aggressive caching

import multiprocessing
import os

# Server socket. Render injects PORT; LightNode keeps the existing 8000 fallback.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Worker configuration - OPTIMIZED for DigitalOcean 2GB RAM
# Strictly restricted to 2 workers to prevent greedy memory consumption since Uvicorn is Async!
workers = int(os.environ.get('WORKERS', '2'))
worker_class = os.environ.get('WORKER_CLASS', 'uvicorn.workers.UvicornWorker')
threads = int(os.environ.get('THREADS', '2'))

# Worker connections (for async workers)
worker_connections = 1000

# Timeout
timeout = 120
keepalive = 5

# Graceful shutdown
graceful_timeout = 30

# Process naming
proc_name = 'pama-api'

# Logging
accesslog = '-'  # stdout
errorlog = '-'   # stdout
loglevel = os.environ.get('LOG_LEVEL', 'info')

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Request-count recycling closes every WebSocket owned by the recycled worker.
# Desktop payment/admission transactions are deliberately short-lived now, but
# they must still never be terminated merely because a worker reached an
# arbitrary request count. Operators can opt back in through the environment
# after confirming that no transactional sockets are active during recycling.
max_requests = int(os.environ.get('MAX_REQUESTS', '0'))
max_requests_jitter = (
    int(os.environ.get('MAX_REQUESTS_JITTER', '0'))
    if max_requests > 0
    else 0
)

# Server identity
server_header = 'PAMA-API'
date_header = False

# Process management
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# ─── Worker ID Injection ─────────────────────────────────────────────────────
# We inject a stable WORKER_ID environment variable (corresponding to the worker slot index)
# into each newly forked process. This ensures that only worker #1 (slot 1) runs
# the background schedulers and migrations, and if that worker restarts, the replacement
# still correctly claims worker slot 1.
def post_fork(server, worker):
    os.environ['WORKER_ID'] = str(worker.age)
