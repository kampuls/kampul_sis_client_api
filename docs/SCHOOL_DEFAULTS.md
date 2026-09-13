# Kampul SIS starter defaults

Every newly provisioned school receives the same versioned starter data from `defaults/kampul_sis.json`. The SQL template contains 212 tables and 1,653 preset rows across 44 tables. Registration details remain in the management platform; they do not customize the school database during provisioning.

| Item | Default |
| --- | --- |
| School / system name | Kampul SIS |
| Branch | Kampul SIS Main Branch, ID 1 |
| App branch display | Kampul SIS |
| Branding | KAMPUL / SIS, built-in school icon |
| Administrator display name and role | Super Admin |
| Username | Random `kampul_admin_` plus 12 hexadecimal characters |
| Password | Independently generated for each school |
| Active academic | 2026-2027, ID 1, unused |
| Student / invoice / receipt prefixes | KMP- / INV- / REC- |
| Cash accounts | Kampul SIS Cash USD and KHR, zero balance |
| Exchange rate | 4,100 KHR/USD, editable |
| Attendance | Default timing settings, no school-specific IP or location requirement |
| Pickup / Telegram / scheduled notifications | Configured defaults, disabled until set up |
| Certificates | KMP- prefix, six digits, landscape |

The shared presets also include curriculum, subjects, grading and marks rules, departments, positions, roles and permissions, global time slots, reference categories and display settings. The Super Admin user is created at provisioning with role 1, branch 1 and full app administrator access. The SQL template deliberately contains no reusable password or source user account.

Business records such as students, parents, invoices, payments and attendance logs start empty. School-specific prices, holidays, media, Telegram credentials and contact information are not fabricated. Settings tied to a real chat or message group are created when that integration/group is configured.

## Change the common defaults

Edit `defaults/kampul_sis.json`, then rebuild. The schema source supplies table definitions only: its branch rows, active academic selection and settings no longer affect starter data. The versioned academic calendar must be updated explicitly when changing the starter academic year.

```powershell
python scripts/build_school_template.py --source 'working test'
$env:RUN_MYSQL_TEMPLATE_TESTS = '1'
python -m pytest tests/test_school_template.py -q
python -m pytest tests/test_desktop_sql.py tests/test_desktop_architecture.py -q
python -m compileall -q app
```

The optional `--presets` and `--out` arguments allow testing a revised preset without replacing the committed SQL template. Missing tables/required columns and invalid branch/year/settings cardinality fail the build. Existing nonempty school databases are never overwritten by provisioning.

## Verification

On 2026-09-13, seven preset tests passed, including creating two separate schools and comparing every preset table while asserting different usernames/passwords. Temporary databases were removed afterward. Foreign-key and curriculum-reference checks passed. Management API build and 28 existing tests passed, plus the new management-side defaults regression test. Client API SQL/architecture checks: 53 passed; the existing deployment check still fails because `.github/workflows/deploy.yml` is missing. Python compilation passed.

The associated Windows desktop at `E:\C# Developer\desktop_to_api\application` reads these defaults through the API. Its architecture check and Debug build passed in the preceding verification; this change modifies server-owned data only.

Changes apply to new schools after the updated API/template is deployed. Existing schools and `working test` were not modified. No production deployment was performed.
