# Certificate push notification image

Place **`notification_certificate.jpg`** in this folder and **commit it to Git**.

## Why this folder (not `uploads/`)

| Path | In Git? | On Lightnode |
|------|---------|----------------|
| `app/static/push/notification_certificate.jpg` | **Yes** — ship with the API | Copied into Docker image on deploy |
| `uploads/push/...` | **No** (gitignored) | Created at runtime on the server |

On API startup and when you **notify parents** on certificate issue, the app:

1. Reads from `app/static/push/notification_certificate.jpg`
2. Uploads to `uploads/push/` (and your configured storage: local / S3 / Cloudinary)
3. Uses `PUBLIC_API_BASE_URL` + `/uploads/push/notification_certificate.jpg` in FCM

## One-time setup (GitHub → Lightnode)

```bash
cd pama_api
# Ensure the artwork is here (copy from Flutter assets if needed):
# cp ../pama_international_school/assets/images/notification_certificate.jpg app/static/push/

git add app/static/push/notification_certificate.jpg app/static/push/README.md
git commit -m "Add certificate push notification image for production"
git push
```

After deploy, verify in the browser:

`https://YOUR_PUBLIC_API_BASE_URL/uploads/push/notification_certificate.jpg`

You should see the JPEG (not `{"detail":"Not Found"}`).

### If you still get 404

1. **Redeploy / restart the API** after `git push` (pull + restart Gunicorn/Docker — not just push to GitHub).
2. On the server, confirm the file exists:
   `ls -la app/static/push/notification_certificate.jpg`
3. After restart, check API logs for: `Certificate push image ready at uploads/push/...`
4. `PUBLIC_API_BASE_URL` in `.env` must be `https://pamais.duckdns.org` (same host you open in the browser).

Set in production `.env`:

```env
PUBLIC_API_BASE_URL=https://pamais.duckdns.org
```

(must match your Lightnode domain and Flutter `_liveUrl` / `shareBaseUrl`.)
