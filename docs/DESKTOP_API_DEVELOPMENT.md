# Desktop API backend guide

Read this guide before changing the API repository.

The Windows desktop application is always online and can access data only
through `/api/desktop`. It has no database driver, credential, local database,
offline mode, or sync process.

The compatibility data router is desktop-token-only. SQL validation must remain
single-statement, parameterized, row-limited, and blocked from schema and
administrative operations. New features should use typed domain endpoints;
do not widen compatibility policy unless existing desktop behavior requires it.

Explicit desktop transactions use one authenticated WebSocket and one database
connection for the socket lifetime. Authentication belongs in the
`Authorization: Bearer` header, never a URL query string.

Media must be uploaded with `StorageService`, and database fields must contain
only URL/path strings for current features. The sole temporary exception is the
pre-existing `students.image` BLOB required by released desktop builds. Current
desktop clients still upload through `StorageService`; the desktop API owns the
narrow tagged compatibility mirror and never returns BLOB bytes over JSON. Do
not add any other `LargeBinary`, `BLOB`, `VARBINARY`, or base64 database fallback.
Startup migration 53 is the one-way bridge for all other legacy binary columns;
migration 57 restores this one field on databases already converted by migration
53, and startup migration 54 owns tables formerly created by WinForms.

Remove the `students.image` exception only after the enforced minimum desktop
version guarantees that no direct-database build remains. That future release
must migrate the final bytes to StorageService, convert the column back to a URL,
and remove the tagged transport plus migration 57 in the same deployment.

Certificate media is shared by Flutter and desktop through
`background_cert.background_url`, `branch.signature_url`, and
`branch.stamp_url`. Migration 56 backfills empty shared URL fields from the
resource paths created by migration 53; clients must not read legacy
certificate media columns afterward.

All WinForms third-party workflows live in the authenticated
`/api/desktop/integrations` router. Provider URLs and credentials are API
configuration/server data only; never return a bot token or accept one from a
desktop request. The integration router owns Telegram delivery, admission-form
consumption, exchange rate, time, map geocoding, version/update metadata, and
installer proxying.

Google Drive certificate upload is intentionally unsupported. Do not restore
OAuth credentials, Drive file IDs, upload/delete routes, or a compatibility
fallback. Certificate PDFs may be forwarded transiently to Telegram but must
not be persisted as database binary data.

Before handoff, run:

```bash
python -m pytest tests/test_desktop_sql.py tests/test_desktop_architecture.py
python -m compileall -q app
```

Also verify the root repository architecture check and desktop build when both
repositories are available.
