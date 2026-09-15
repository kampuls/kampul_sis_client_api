from pathlib import Path
import re
import pytest


API_ROOT = Path(__file__).resolve().parents[1]


def test_no_model_declares_database_binary_media():
    """Media lives in storage as URL paths, never as bytes in a column.

    students.image was the last exception, held as a BLOB only while already
    released desktop builds still required one. The universal binary-media
    migration moved it to VARCHAR(255) URL paths, so no exception remains.
    """
    forbidden = re.compile(r"\bLargeBinary\b|\b(?:TINYBLOB|MEDIUMBLOB|LONGBLOB|VARBINARY)\b", re.I)
    violations = []
    for path in (API_ROOT / "app" / "models").rglob("*.py"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            violations.append(path.relative_to(API_ROOT).as_posix())
    assert violations == []
    student_model = (API_ROOT / "app" / "models" / "student.py").read_text(encoding="utf-8")
    assert "image = Column(String(255), nullable=True)" in student_model


def test_desktop_router_and_media_compatibility_migrations_exist():
    router = (API_ROOT / "app" / "api" / "desktop" / "data.py").read_text(encoding="utf-8")
    migrations = (API_ROOT / "app" / "core" / "migrations.py").read_text(encoding="utf-8")

    assert '@router.post("/command"' in router
    assert '@router.post("/resources"' in router
    assert '@router.delete("/resources"' in router
    assert '@router.websocket("/transaction"' in router
    assert "_detect_resource_content_type(content)" in router
    assert "_migrate_all_binary_media_to_resources(connection)" in migrations
    assert "_migrate_desktop_owned_tables(connection)" in migrations
    assert "_migrate_certificate_resource_url_fields(connection)" in migrations
    assert "_migrate_legacy_student_image_blob_compatibility(connection)" in migrations
    # The universal migration moves every binary column out to a storage URL,
    # so no migration may convert a column back into a BLOB.
    blob_conversions = re.findall(
        r"ALTER\s+TABLE\s+`?(\w+)`?\s+MODIFY\s+COLUMN\s+`?(\w+)`?\s+(?:MEDIUM|LONG|TINY)?BLOB",
        migrations,
        re.I,
    )
    assert blob_conversions == []
    assert (
        "ALTER TABLE `students` MODIFY COLUMN `image` VARCHAR(255) NULL"
        in migrations
    )


def test_student_avatar_compatibility_repairs_and_supplies_resource_defaults():
    router = (API_ROOT / "app" / "api" / "desktop" / "data.py").read_text(
        encoding="utf-8"
    )
    migrations = (API_ROOT / "app" / "core" / "migrations.py").read_text(
        encoding="utf-8"
    )
    model = (API_ROOT / "app" / "models" / "user_resource.py").read_text(
        encoding="utf-8"
    )

    required_insert_columns = "user_id, user_type, avatar, cover_focus_y,"
    assert required_insert_columns in router
    assert required_insert_columns in migrations
    assert "MODIFY COLUMN cover_focus_y INT NOT NULL DEFAULT 0" in migrations
    assert 'server_default="0"' in model


def test_existing_user_resource_without_cover_focus_default_is_repaired():
    from app.core.migrations import _migrate_create_user_resources_table

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.statements = []
            self.commits = 0

        def execute(self, statement):
            sql = str(statement)
            self.statements.append(sql)
            if "information_schema.TABLES" in sql:
                return Result((1,))
            if "COLUMN_NAME = 'avatar'" in sql:
                return Result(("varchar",))
            if "COLUMN_NAME = 'cover_focus_y'" in sql:
                return Result(("NO", None))
            return Result(None)

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("repair should not roll back")

    connection = Connection()
    _migrate_create_user_resources_table(connection)

    executed = "\n".join(connection.statements)
    assert "SET cover_focus_y = 0" in executed
    assert "MODIFY COLUMN cover_focus_y INT NOT NULL DEFAULT 0" in executed
    assert connection.commits == 1


def test_desktop_external_workflows_are_authenticated_api_integrations():
    package_router = (API_ROOT / "app" / "api" / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )
    integrations = (API_ROOT / "app" / "api" / "desktop" / "integrations.py").read_text(
        encoding="utf-8"
    )

    assert "integrations_router" in package_router
    assert 'prefix="/integrations"' in package_router
    for route in (
        '/telegram/message',
        '/telegram/document',
        '/admission-form/{form_key}/consume',
        '/exchange-rate',
        '/time',
        '/map/search',
        '/required-version',
        '/update/manifest',
        '/update/download',
    ):
        assert route in integrations

    assert integrations.count("Depends(get_current_desktop_user)") >= 9
    assert "bot_token:" not in integrations
    assert "GoogleDrive" not in integrations


def test_desktop_dashboard_is_typed_authenticated_and_branch_scoped():
    package_router = (API_ROOT / "app" / "api" / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )
    dashboard = (API_ROOT / "app" / "api" / "desktop" / "dashboard.py").read_text(
        encoding="utf-8"
    )

    assert "dashboard_router" in package_router
    assert 'prefix="/dashboard"' in package_router
    assert '@router.get("/overview")' in dashboard
    assert "academic_id: int = Query(0, ge=0)" in dashboard
    assert ":today BETWEEN DATE(academic_start) AND DATE(academic_end)" in dashboard
    assert "Depends(get_current_desktop_user)" in dashboard
    assert '_has_permission(db, role_id, "ViewDashboard")' in dashboard
    assert '_has_permission(db, role_id, "DashboardBasic")' in dashboard
    assert '_has_permission(db, role_id, "DashboardAccounting")' in dashboard
    assert '_has_permission(db, role_id, "ViewAllBranches")' in dashboard
    assert '"can_view_basic": can_view_basic' in dashboard
    assert '"can_view_accounting": can_view_accounting' in dashboard
    assert '"recent_payments": recent_payments if can_view_accounting else []' in dashboard
    assert "if user_branch_id <= 0:" in dashboard
    assert "def _json_number(value: Any) -> float:" in dashboard
    assert "return float(Decimal(str(value)))" in dashboard
    assert "_decimal(" not in dashboard
    assert "compatibility" not in dashboard.lower()


def test_desktop_notifications_share_the_authenticated_flutter_staff_inbox():
    package_router = (API_ROOT / "app" / "api" / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )
    notifications = (
        API_ROOT / "app" / "api" / "desktop" / "notifications.py"
    ).read_text(encoding="utf-8")

    assert "notifications_router" in package_router
    assert 'prefix="/notifications"' in package_router
    assert 'STAFF_NOTIFICATION_USER_TYPE = "teacher"' in notifications
    assert "Depends(get_current_desktop_user)" in notifications
    assert '@router.get("")' in notifications
    assert '@router.post("/read-all")' in notifications
    assert '@router.post("/{notification_id}/read")' in notifications
    assert '@router.post("/{notification_id}/unread")' in notifications
    assert '@router.delete("/{notification_id}")' in notifications
    assert "Notification.user_id == int(current_user.id)" in notifications


def test_desktop_leave_reuses_the_authenticated_canonical_workflow():
    package_router = (API_ROOT / "app" / "api" / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )
    leave_router = (API_ROOT / "app" / "api" / "desktop" / "leave.py").read_text(
        encoding="utf-8"
    )

    assert "leave_management_router" in package_router
    assert 'prefix="/leave-management"' in package_router
    assert "dependencies=[Depends(get_current_desktop_user)]" in package_router
    assert "shared_leave_router" in leave_router
    assert "router.include_router(shared_leave_router)" in leave_router
    assert "Depends(get_current_desktop_user)" in leave_router
    assert "connection string" not in leave_router.lower()
    assert "mysql" not in leave_router.lower()


def test_desktop_update_download_url_is_server_selected():
    integrations = (API_ROOT / "app" / "api" / "desktop" / "integrations.py").read_text(
        encoding="utf-8"
    )

    gateway = (API_ROOT / "app" / "services" / "kampul_releases.py").read_text(encoding="utf-8")
    assert "download_url: str" not in integrations
    assert "f'{base}/{version}/download'" in integrations
    assert "follow_redirects=False" in integrations
    assert "parsed.hostname != 'sis.kampul.com'" in gateway
    assert "X-Kampul-Service-Token" in gateway
    assert "await catalog(db)" in integrations


def test_large_api_responses_enable_transport_compression():
    main_module = (API_ROOT / "app" / "main.py").read_text(encoding="utf-8")

    assert "from fastapi.middleware.gzip import GZipMiddleware" in main_module
    assert "app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)" in main_module


def test_gunicorn_does_not_recycle_transaction_websocket_workers_by_default():
    gunicorn_config = (API_ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")

    assert "os.environ.get('MAX_REQUESTS', '0')" in gunicorn_config
    assert "os.environ.get('MAX_REQUESTS_JITTER', '0')" in gunicorn_config
    assert "max_requests = 1000" not in gunicorn_config


def test_production_deploy_preserves_telegram_login_configuration():
    deploy_file = API_ROOT / ".github" / "workflows" / "deploy.yml"
    if not deploy_file.exists():
        pytest.skip("Legacy LightNode deploy workflow removed in favor of OVHcloud VPS")
    compose = (API_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    workflow = deploy_file.read_text(
        encoding="utf-8"
    )

    # Compose merges env_file entries in order. Keep historical application
    # secrets while allowing LightNode's database/runtime values to take priority.
    assert compose.index("- config/.env") < compose.index("- .env.lightnode")
    assert "settings.telegram_api_id and settings.telegram_api_hash" in workflow
    assert "TELEGRAM_API_ID: ${{ secrets.TELEGRAM_API_ID }}" in workflow
    assert "TELEGRAM_API_HASH: ${{ secrets.TELEGRAM_API_HASH }}" in workflow
    assert "envs: TELEGRAM_API_ID,TELEGRAM_API_HASH" in workflow
    assert "TELEGRAM_API_ID=%s\\nTELEGRAM_API_HASH=%s" in workflow
