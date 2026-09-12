# LightNode Super-Server Management Guide

This guide provides everything you or future developers need to know to securely access, manage, and monitor the Pama API production environment running on your massive 8GB LightNode instance.

## 1. Quick Server Access
To connect directly to the live server terminal from your local machine, open your terminal and run the following SSH command from the root of your `pama_api` repository:

```bash
ssh -i ./deploy_key root@38.60.169.172
```
Once connected, navigate to the production codebase:
```bash
cd /root/pama_api
```

## 2. Viewing Live API Logs
If a user reports an issue or you want to see incoming network traffic natively, you can tail the live Docker container logs. Run this while SSH'd into the server:

```bash
# View the last 100 API request logs
docker logs --tail=100 pama_api

# "Follow" the logs live (press Ctrl+C to exit)
docker logs -f pama_api
```

## 3. Managing Environment Variables
The LightNode environment is securely injected using variables from GitHub and Docker. 
If you need to change a production key (e.g., Firebase Token, Google Client ID, JWT Secret):

1. Edit the file locally: `pama_api/.env.digitalocean`
2. Commit and push the file to GitHub.
3. The GitHub Actions CI/CD bot will automatically secure-copy it to the Server as `.env` and restart the backend.

If you edit the `.env` directly on the server instead, you MUST restart the Docker container for it to take effect:
```bash
# Restart only the API (leaves database running perfectly)
docker compose restart api
```

## 4. Docker Container Commands
The LightNode server uses `docker compose` to run 3 microservices: `api` (Python), `mysql` (Database), and `redis` (Cache).

- **See what is running:** `docker ps`
- **Fully reboot everything:** `docker compose down && docker compose up -d`
- **Rebuild after making code changes manually on Server:** `docker compose up -d --build api`

## 5. Deployment Flow (CI/CD)
You **do not** need to manually deploy code! 
We have built an automated GitHub Actions pipeline located at `.github/workflows/deploy.yml`.

Whenever any developer runs:
```bash
git add .
git commit -m "Update feature"
git push origin main
```
1. GitHub intercepts the code.
2. It completely securely connects to the `38.60.169.172` Server via SSH.
3. It `rsync`s all the new python files over instantly.
4. It safely restarts the Gunicorn API workers with zero downtime.

## 6. Firebase Service Account (FCM Push Notifications)

The `config/firebase-service-account.json` file is **gitignored** (it contains a private key) and lives **permanently on the LightNode server**.

The rsync step in `deploy.yml` excludes it (`--exclude 'config/firebase-service-account.json'`) so the `--delete` flag never wipes it during deployments.

### If the file is ever lost (e.g., server rebuild), copy it once from local:
```bash
scp -i ./deploy_key config/firebase-service-account.json root@38.60.169.172:/root/pama_api/config/firebase-service-account.json
ssh -i ./deploy_key root@38.60.169.172 "cd /root/pama_api && docker compose restart api"
```
You only need to do this **once** — future deploys will never delete it.

## 7. Known Architecture Notes
- **Workers Configuration:** Gunicorn is configured dynamically to exploit your 8GB RAM flawlessly! We run an incredible **`8` Uvicorn workers**. We explicitly inject `WORKER_ID` strings so that Database Migrations ONLY run on the primary worker, securely protecting against MySQL Deadlocks.
- **Port Masking:** Even though the flutter app calls `http://38.60.169.172` without a port, the LightNode Server is actively running an unseen native NGINX proxy on Port 80 which instantly bridges traffic straight to our Docker port `8000`.
- **Cloud deployment status:** LightNode, FastAPI Cloud, and Render deploy automatically from `main`. FastAPI Cloud and Render keep `AUTO_MIGRATE_ON_STARTUP=false` and `BACKGROUND_JOBS_ENABLED=false`, so they do not run migrations or duplicate LightNode's scheduled jobs.
- **Render free-service keepalive:** Render alone sets `RENDER_KEEPALIVE_ENABLED=true` and `RENDER_KEEPALIVE_INTERVAL_SECONDS=840`. The API uses Render's injected `RENDER_EXTERNAL_URL` and accepts only an HTTPS `*.onrender.com` target. The feature defaults to off, so copying or deploying the code to LightNode/FastAPI Cloud does not start it.

## 7. Database Remote Access (Local Clients)
Even though the application code connects to `db` internally, you can securely access the live production MySQL database from your local machine using tools like DBeaver, TablePlus, or DataGrip. Keep in mind you may need to open TCP Port `3306` inside the **LightNode Web Console Firewall**.

**Connection Details:**
* **Host:** `pamais.duckdns.org` (or IP: `38.60.169.172`)
* **Port:** `3306`
* **Database Name:** `pamais`
* **Username:** `pamais` (or `root`)
* **Password:** read from the `PAMAIS_DB_PASSWORD` environment variable

*Warning:* SSH root authentication uses a separate credential, read from
`PAMAIS_SSH_PASSWORD`. Do not confuse the SSH server credentials with the
database connection credentials.

*Never commit either value.* Both were previously written out in this file and
are therefore still recoverable from this repository's history, so they must be
treated as compromised and rotated. Keep them in your shell environment or a
secrets manager instead:

```bash
export PAMAIS_DB_PASSWORD='...'
export PAMAIS_SSH_PASSWORD='...'
```
