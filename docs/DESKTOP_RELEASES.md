# Kampul SIS desktop releases

The release authority is https://sis.kampul.com. GitHub may host source code, but is no longer an installer, manifest or minimum-version provider. Desktop 2.3.0 uses its school API to authenticate, obtain Kampul release policy, and download a specific version. The school API makes authenticated server-to-server calls to the central Kampul API.

## What is enforced

- Website downloads require a signed-in school owner with an active, unexpired, unsuspended, non-trial tenant and a paid non-trial invoice with a positive amount.
- Desktop downloads require a valid desktop login and the same live school subscription check. A school code alone never authorizes download.
- The latest three numeric versions are retained. Publishing 3.1.2 after 3.1.1, 3.1.0 and 3.0.0 retains 3.1.2, 3.1.1 and 3.1.0 and deletes 3.0.0. Downloads of removed releases return 404.
- Releases are immutable and strictly increasing. The catalog changes only after the complete installer passes size, executable-header and SHA-256 checks. Publishing is serialized using a filesystem lock.
- Default publishing makes the new version mandatory. An explicit minimum version must be a retained release and cannot decrease. The desktop offers the latest release; API data commands and new WebSocket transactions enforce the minimum version.
- The desktop verifies exact size and SHA-256 after downloading and immediately before installation. MD5-only files are rejected. Download URLs are selected by the server and pinned to the selected version.
- Version-policy failures block use. Update endpoints remain reachable to authenticated paid users running an old version so they can upgrade.

SHA-256 over authenticated HTTPS checks download integrity; it is not a publisher signature or proof that a client binary has not been modified. The version header enforces supported-client policy, not remote binary attestation. Sign production installers using a trusted Windows Authenticode certificate when available. The current local 2.3.0 build is not publisher-signed; no signing certificate was configured.

## One-time server setup

Deploy the NestJS backend changes, Next.js download-page changes, and the Python school API gateway changes together. Both API copies in the workspace have the gateway updates: `kampul_sis_client_api` and desktop `pama_api`.

Set on the central NestJS process:

```text
DESKTOP_RELEASE_DIR=/var/lib/kampul/desktop-releases
DESKTOP_RELEASE_PUBLISH_KEY=<independent random secret of at least 32 characters>
KAMPUL_RELEASE_SERVICE_TOKEN=<different random secret of at least 32 characters>
```

Set on each Python school API process:

```text
KAMPUL_RELEASE_API_URL=https://sis.kampul.com
KAMPUL_RELEASE_SERVICE_TOKEN=<same server-to-server secret as central API>
KAMPUL_SCHOOL_SLUG=<registered tenant subdomain, for a legacy non-sis_ database>
```

For databases named `sis_my_school`, the gateway derives `my-school` from the actual connected database. It does not trust a client-supplied subscription identity. Keep this shared service secret only on trusted API servers. Remove obsolete `DESKTOP_REQUIRED_VERSION_URL` and `DESKTOP_UPDATE_MANIFEST_URL` settings.

Create the private release directory owned by the backend service user, with restrictive filesystem permissions. Persist it across deployments/container recreation. Do not expose it through Nginx aliases, Next.js public files, a CDN bucket or a static-file route. All backend workers must share the same filesystem. Back up the catalog and installers together.

Route `/api/desktop-releases/` directly to NestJS on port 4001 at the existing Kampul origin. For Nginx, merge the following into the existing server configuration (do not replace unrelated locations):

```nginx
location /api/desktop-releases/ {
    client_max_body_size 9m;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_read_timeout 1800s;
    proxy_send_timeout 1800s;
    proxy_pass http://127.0.0.1:4001;
}
```

The publisher sends 8 MiB chunks, avoiding a large single request. A failed upload never becomes a release. Incomplete chunks remain under `incoming`; administrators may remove abandoned upload directories when no publisher is using them. If the process crashes with `.publish.lock` present, confirm no publishing process is running before removing that lock. Do not expose secrets in logs or command-line arguments.

Remove any previous public Windows installers from the deployed web public/downloads directory and purge any cached copies. The workspace copy was moved into a gitignored private legacy-installers folder. Previously public GitHub assets need separate removal/restriction if they must no longer be accessible; changing this updater does not revoke already downloaded copies.

## Initial rollout order

1. Deploy the central release API and configure its private storage and two secrets.
2. Publish the verified 2.3.0 installer to the central server using the command below.
3. Verify the signed-in paid-owner download from the portal and confirm logged-out/expired accounts receive 401/403.
4. Deploy the Python gateway configuration and frontend changes. The catalog must exist before enabling the new mandatory policy or all desktops will fail closed.
5. Install 2.3.0 from the authenticated portal on one school PC and check login, update verification and normal data access. Older clients without the new size/version headers may need this one-time manual installer from the portal.
6. Confirm the school code resolves through sis.kampul.com. The desktop no longer defaults to the unrelated las.kampul.com school.

## Every new version

Run from the desktop repository. Supply the publish key through the process environment/secret manager, not a committed file. Build and test locally first:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-installer.ps1 -Version 2.3.1
powershell -ExecutionPolicy Bypass -File scripts/check-desktop-api-architecture.ps1
powershell -ExecutionPolicy Bypass -File scripts/test-update-integrity.ps1
```

The build updates both assembly versions and the installer version. It writes the installer under `releases`. A normal build does not publish or change live update policy.

To build and publish in one command after verification:

```powershell
.\scripts\publish-release.ps1 -Version 2.3.1 -Changelog 'Describe the user-visible fixes.'
```

To upload an already built installer, including a signed installer:

```powershell
.\scripts\publish-release.ps1 -Version 2.3.1 -InstallerPath 'releases\Kampul-SIS-Setup-v2.3.1-14092026.exe' -Changelog 'Describe the fixes.' -RequireSigned
```

Omit `-RequireSigned` only if publishing an unsigned build is intentional. Sign before upload; signing changes SHA-256. To allow an older supported version while recommending the newest, add `-MinimumVersion 2.3.0` while that version is still retained. The default minimum equals the new release.

The script hashes the installer, starts an authenticated upload, transfers chunks, and commits the release. It checks that the server returns the requested version and matching SHA-256. Only then does retention remove the fourth-oldest version. Never reuse a published version number. Fix a bad release by publishing a higher version.

## API routes

- `GET /api/desktop-releases`: signed-in paid owner or authenticated school API; catalog with latest-first retained releases and minimumVersion.
- `GET /api/desktop-releases/:version/download`: same access checks on every download.
- `POST /api/desktop-releases/uploads`: publish-key authenticated upload metadata.
- `POST /api/desktop-releases/uploads/:id/:index`: publish-key authenticated binary chunk.
- `POST /api/desktop-releases/uploads/:id/complete/commit`: verify, publish and prune.
- School desktop compatibility: `/api/desktop/integrations/update/releases`, `/update/manifest`, `/update/download?version=2.3.0`, and `/required-version`.

The release publishing key and service token are separate privileges. Neither belongs in WinForms, browser JavaScript, a manifest or a download link.

## Local verification and current status

Built 2.3.0 on 2026-09-13. Installer: `releases/Kampul-SIS-Setup-v2.3.0-13092026.exe` (about 102 MiB).
SHA-256: `483966F4C2B814D49AFF54DFEF537CB92AFA09139843656675C6EEBC551D261A`.

Passed: desktop Debug and Release builds, Inno installer build, desktop architecture check, actual desktop hash/tamper/MD5-rejection checks, backend release HTTP/subscription/retention/chunk tests, website production build, client API checks (56 passed, one unrelated deployment test skipped), desktop API checks (43 passed). The website build logged an unavailable local backend during prerendering but completed successfully.

Production was not changed: the configured SSH target rejected available credentials and no publishing key was available in this session. Complete the one-time setup and rollout above before distributing this mandatory-update client.
