# FastAPI Cloud Deployment

This project supports FastAPI Cloud in addition to the existing LightNode
deployment.

## Runtime

The committed `.python-version` file pins FastAPI Cloud to Python 3.11. The
application's current dependency versions have pre-built Python 3.11 wheels,
while `pydantic-core==2.33.2` cannot build with the Python 3.14 runtime that
FastAPI Cloud selects by default.

This setting does not change LightNode. LightNode continues to build from the
root `Dockerfile`, which explicitly uses `python:3.11.5-slim`, and continues to
start the app with Gunicorn.

## Deploy

Run deployment commands from the API directory:

```bash
cd pama_api
fastapi deploy
```

FastAPI Cloud automatically detects the application at `app/main.py` and its
dependencies in `requirements.txt`.

## Environment variables

Configure the FastAPI Cloud app's environment variables in its dashboard before
deploying. At minimum, this application requires:

- `SECRET_KEY`
- `DEEPSEEK_API_KEY`
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

Production deployments should also configure `ENVIRONMENT=production`,
`ALLOWED_HOSTS`, `CORS_ORIGINS`, and the optional database SSL, Firebase,
storage, email, and Telegram settings used by the enabled features.

For Firebase Cloud Messaging on a fileless cloud runtime, store the service
account JSON as the encrypted `FCM_SERVICE_ACCOUNT_JSON` variable. LightNode
continues using `FCM_SERVICE_ACCOUNT_PATH`.

When FastAPI Cloud and LightNode use the same production database, configure
these values on FastAPI Cloud:

```dotenv
AUTO_MIGRATE_ON_STARTUP=false
BACKGROUND_JOBS_ENABLED=false
```

LightNode remains the primary instance responsible for database migrations,
schedule reminders, notification cleanup, and other recurring jobs. FastAPI
Cloud serves requests without running a second copy of those tasks.

Use FastAPI Cloud secrets for passwords, API keys, tokens, and private
credentials. Do not upload a LightNode `.env` file to FastAPI Cloud.
