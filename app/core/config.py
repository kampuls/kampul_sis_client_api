from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional
import os
import secrets


class Settings(BaseSettings):
    # Environment
    environment: str = Field(
        default="development", alias="ENVIRONMENT"
    )  # development, staging, production

    # Database settings - loaded from environment variables
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=3306, alias="DB_PORT")
    db_user: str = Field(default="root", alias="DB_USER")
    db_password: str = Field(default="", alias="DB_PASSWORD")
    db_name: str = Field(default="pama_db", alias="DB_NAME")

    # Database connection pool settings for production
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=50, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=60, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(
        default=3600, alias="DB_POOL_RECYCLE"
    )  # Recycle connections every hour

    # SSL/TLS settings for MySQL - optional
    db_ssl_ca: Optional[str] = Field(
        default=None, alias="DB_SSL_CA"
    )  # Path to CA certificate file (ca.pem)
    db_ssl_cert: Optional[str] = Field(
        default=None, alias="DB_SSL_CERT"
    )  # Path to client certificate file
    db_ssl_key: Optional[str] = Field(
        default=None, alias="DB_SSL_KEY"
    )  # Path to client private key file
    db_ssl_mode: str = Field(
        default="PREFERRED", alias="DB_SSL_MODE"
    )  # SSL mode: DISABLED, PREFERRED, REQUIRED, VERIFY_CA, VERIFY_IDENTITY

    @property
    def database_url(self) -> str:
        env_url = os.getenv("DATABASE_URL")
        if env_url:
            if env_url.startswith("postgres://"):
                env_url = env_url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif env_url.startswith("postgresql://") and not env_url.startswith("postgresql+"):
                env_url = env_url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return env_url
        import urllib.parse
        encoded_pwd = urllib.parse.quote_plus(self.db_password)
        return f"mysql+pymysql://{self.db_user}:{encoded_pwd}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def ssl_config(self) -> dict:
        """Get SSL configuration for MySQL connection"""
        ssl_config = {}

        if self.db_ssl_ca:
            # If path is relative, make it absolute from project root
            if not os.path.isabs(self.db_ssl_ca):
                # app/core/config.py -> app/core -> app -> root
                root_dir = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                ca_path = os.path.join(root_dir, self.db_ssl_ca)
            else:
                ca_path = self.db_ssl_ca

            if os.path.exists(ca_path):
                ssl_config["ssl_ca"] = ca_path
            else:
                # IMPORTANT: If we crash here, the whole app fails startup (500 error).
                # Better to warn and proceed without CA (connection might fail later, but at least app starts).
                print(
                    f"WARNING: SSL CA file not found at {ca_path}. Proceeding without it."
                )

        if self.db_ssl_cert:
            ssl_config["ssl_cert"] = self.db_ssl_cert
        if self.db_ssl_key:
            ssl_config["ssl_key"] = self.db_ssl_key

        # Set SSL mode
        ssl_config["ssl_disabled"] = self.db_ssl_mode == "DISABLED"

        return ssl_config

    # JWT settings - loaded from environment variables
    # SECURITY: secret_key MUST be set via environment variable in production
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    short_lived_token_hours: int = Field(
        default=2, alias="SHORT_LIVED_TOKEN_HOURS"
    )  # 2 hours (Facebook-like)
    long_lived_token_days: int = Field(
        default=60, alias="LONG_LIVED_TOKEN_DAYS"
    )  # 60 days (Facebook-like, can be refreshed/extended)
    desktop_token_hours: int = Field(
        default=12, alias="DESKTOP_TOKEN_HOURS"
    )

    # Security settings
    password_min_length: int = Field(default=8, alias="PASSWORD_MIN_LENGTH")
    password_require_uppercase: bool = Field(
        default=True, alias="PASSWORD_REQUIRE_UPPERCASE"
    )
    password_require_lowercase: bool = Field(
        default=True, alias="PASSWORD_REQUIRE_LOWERCASE"
    )
    password_require_numbers: bool = Field(
        default=True, alias="PASSWORD_REQUIRE_NUMBERS"
    )
    password_require_special: bool = Field(
        default=True, alias="PASSWORD_REQUIRE_SPECIAL"
    )
    # Development-only legacy phone flow. It uses a fixed OTP and must remain
    # disabled unless a developer explicitly opts in on a non-production box.
    allow_insecure_static_phone_otp: bool = Field(
        default=False, alias="ALLOW_INSECURE_STATIC_PHONE_OTP"
    )
    # Rollout bridge for official app versions before 1.2.8, which cannot send
    # the per-install primary attendance-phone identity. It is disabled by
    # default because User-Agent/version headers are not proof of app identity.
    # A controlled short rollout may opt in explicitly, but production should
    # keep this false to prevent bypassing the primary-phone binding.
    allow_legacy_attendance_device_compat: bool = Field(
        default=False,
        alias="ALLOW_LEGACY_ATTENDANCE_DEVICE_COMPAT",
    )

    # Rate limiting
    # 10000 requests per 60s per IP — covers ~166 req/s per client before blocking.
    # A real school user does at most 3-5 req/s, so this never blocks legitimate users.
    # Bots/scrapers hitting 166+ req/s will be blocked. Server capacity is ~400 req/s.
    # Override via Render env var RATE_LIMIT_REQUESTS (no redeploy required).
    rate_limit_requests: int = Field(default=10000, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=60, alias="RATE_LIMIT_WINDOW")  # seconds

    # Password-guessing throttle for the login endpoints. The global rate limit
    # above is far too loose to stop a brute force (10k/min is ~166 guesses a
    # second) and it buckets on a client-supplied header, so this counts failures
    # per ACCOUNT as well, which IP rotation cannot dodge.
    # Chosen so a real person mistyping a password never notices.
    login_throttle_enabled: bool = Field(
        default=True, alias="LOGIN_THROTTLE_ENABLED"
    )
    # Hard-lock accounts whose phone is shared with another account of the same
    # kind. Refusing the ambiguous PHONE login is never optional — that is the
    # coin flip that signs someone into a stranger's account. This flag only
    # controls the additional block on username/password login and /me, which
    # is what actually locks a person out of the app.
    #
    # Defaults to FALSE on purpose. The audit on live data found 106 accounts
    # sharing a number with another account of the same kind, so a default of
    # true would lock all of them out of the app the moment this deploys —
    # before anyone has had a chance to clean the data up. Nothing is lost by
    # waiting: the ambiguous PHONE login is refused regardless of this flag, so
    # the wrong-account coin flip is already closed. Turn this on once
    # scripts/audit_phone_conflicts.py reports zero.
    phone_conflict_lock_enabled: bool = Field(
        default=False, alias="PHONE_CONFLICT_LOCK_ENABLED"
    )
    login_max_failed_attempts: int = Field(
        default=10, alias="LOGIN_MAX_FAILED_ATTEMPTS"
    )
    login_attempt_window_seconds: int = Field(
        default=900, alias="LOGIN_ATTEMPT_WINDOW_SECONDS"
    )

    # Telegram OTP is a public, provider-billed login-code surface.  Keep a
    # tighter per-phone limit and a school-NAT-friendly per-IP limit instead of
    # relying on the intentionally broad global API limiter.
    telegram_otp_throttle_enabled: bool = Field(
        default=True, alias="TELEGRAM_OTP_THROTTLE_ENABLED"
    )
    telegram_otp_max_sends_per_phone: int = Field(
        default=5, alias="TELEGRAM_OTP_MAX_SENDS_PER_PHONE"
    )
    telegram_otp_max_sends_per_ip: int = Field(
        default=30, alias="TELEGRAM_OTP_MAX_SENDS_PER_IP"
    )
    telegram_otp_window_seconds: int = Field(
        default=900, alias="TELEGRAM_OTP_WINDOW_SECONDS"
    )
    telegram_registration_proof_ttl_seconds: int = Field(
        default=1800, alias="TELEGRAM_REGISTRATION_PROOF_TTL_SECONDS"
    )

    # CORS settings
    # SECURITY: Do NOT use wildcard "*" in production - specify exact origins
    cors_origins: list = Field(
        default=[], alias="CORS_ORIGINS"
    )  # Must specify production origins (e.g., ["https://pamais.onrender.com"])
    cors_methods: list = Field(
        default=["GET", "POST", "PUT", "DELETE", "PATCH"], alias="CORS_METHODS"
    )
    cors_headers: list = Field(default=["*"], alias="CORS_HEADERS")

    # Allowed hosts - SECURITY: Must specify production hostnames
    allowed_hosts: list = Field(
        default=[], alias="ALLOWED_HOSTS"
    )  # e.g., ["pamais.onrender.com"]

    # App settings - loaded from environment variables
    app_name: str = Field(default="Kampul SIS Client API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    # Public school name for /privacy and /terms (falls back to APP_NAME without " API").
    app_display_name: str = Field(default="", alias="APP_DISPLAY_NAME")
    # Optional fixed effective date for legal pages (e.g. "March 2026").
    # Empty = auto current Month Year at request time.
    legal_effective_date: str = Field(default="", alias="LEGAL_EFFECTIVE_DATE")
    support_phone: str = Field(default="0962514196", alias="SUPPORT_PHONE")
    support_telegram_url: str = Field(
        default="https://t.me/rornpisith",
        alias="SUPPORT_TELEGRAM_URL",
    )
    # Mobile app identity for /leave, /form, /app/download, and .well-known links.
    # Defaults keep PAMA production; override per school deployment.
    mobile_app_short_name: str = Field(default="PAMAIS", alias="MOBILE_APP_SHORT_NAME")
    android_application_id: str = Field(
        default="com.pamais.edu.kh",
        alias="ANDROID_APPLICATION_ID",
    )
    ios_bundle_id: str = Field(
        default="com.pamais.edu.kh",
        alias="IOS_BUNDLE_ID",
    )
    ios_team_id: str = Field(default="G8X75BJYQB", alias="IOS_TEAM_ID")
    ios_app_store_id: str = Field(default="6759542788", alias="IOS_APP_STORE_ID")
    ios_app_store_slug: str = Field(
        default="pama-international-school",
        alias="IOS_APP_STORE_SLUG",
    )
    deep_link_scheme: str = Field(default="pamais", alias="DEEP_LINK_SCHEME")
    # Comma-separated SHA-256 fingerprints for Android App Links.
    android_sha256_cert_fingerprints: str = Field(
        default="18:DF:B4:DA:AD:CE:FF:24:10:AA:A5:36:1C:C0:54:06:A6:7F:73:57:79:3E:98:0D:E3:04:4E:A1:F9:E0:8F:85",
        alias="ANDROID_SHA256_CERT_FINGERPRINTS",
    )
    # Version checking removed - Flutter app checks stores directly now
    debug: bool = Field(default=False, alias="DEBUG")  # Default to False for production

    # Server settings
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8080, alias="PORT")
    workers: int = Field(default=1, alias="WORKERS")  # Number of worker processes
    # The WinForms client is always-online. This switch can immediately stop
    # its privileged compatibility surface without affecting mobile/web APIs.
    desktop_api_enabled: bool = Field(default=True, alias="DESKTOP_API_ENABLED")
    desktop_api_max_rows: int = Field(
        default=100000,
        alias="DESKTOP_API_MAX_ROWS",
        ge=1,
        le=500000,
    )
    desktop_resource_max_mb: int = Field(
        default=20,
        alias="DESKTOP_RESOURCE_MAX_MB",
        ge=1,
        le=100,
    )
    # All third-party workflows used by the WinForms client are brokered by
    # authenticated /api/desktop/integrations endpoints.  Keeping these URLs
    # here prevents provider details and credentials from leaking into desktop
    # builds and allows deployments to change providers without rebuilding it.
    desktop_external_timeout_seconds: int = Field(
        default=30,
        alias="DESKTOP_EXTERNAL_TIMEOUT_SECONDS",
        ge=5,
        le=300,
    )
    desktop_admission_firebase_url: str = Field(
        default="https://pamais-server-default-rtdb.asia-southeast1.firebasedatabase.app/",
        alias="DESKTOP_ADMISSION_FIREBASE_URL",
    )
    desktop_exchange_rate_url: str = Field(
        default="https://data.mef.gov.kh/api/v1/realtime-api/exchange-rate?currency_id=USD",
        alias="DESKTOP_EXCHANGE_RATE_URL",
    )
    desktop_geocoding_url: str = Field(
        default="https://nominatim.openstreetmap.org/search",
        alias="DESKTOP_GEOCODING_URL",
    )
    desktop_required_version_url: str = Field(
        default="https://raw.githubusercontent.com/pamais-school/version/main/checking.txt",
        alias="DESKTOP_REQUIRED_VERSION_URL",
    )
    desktop_update_manifest_url: str = Field(
        default="https://github.com/pamais/asdupdate/releases/latest/download/update.txt",
        alias="DESKTOP_UPDATE_MANIFEST_URL",
    )
    # Public browser origin used for Telegram/app links and public assets.
    # Change these deployment variables when the server domain changes; no
    # source-code update is required. PAMA_APP_LINK_BASE_URL may point app
    # links at a different origin, otherwise PUBLIC_API_BASE_URL is used.
    public_api_base_url: str = Field(default="", alias="PUBLIC_API_BASE_URL")
    pama_app_link_base_url: str = Field(
        default="",
        alias="PAMA_APP_LINK_BASE_URL",
    )
    # Comma-separated CIDRs/IPs of reverse proxies that are allowed to supply
    # X-Forwarded-For. Empty means forwarded client-IP headers are never trusted.
    trusted_proxy_ranges: str = Field(default="", alias="TRUSTED_PROXY_RANGES")
    auto_migrate_on_startup: bool = Field(
        default=True, alias="AUTO_MIGRATE_ON_STARTUP"
    )
    background_jobs_enabled: bool = Field(
        default=True, alias="BACKGROUND_JOBS_ENABLED"
    )
    # Optional keepalive for a Render free web service. It is disabled by
    # default so LightNode, FastAPI Cloud, and local development are unaffected.
    # When enabled on Render, RENDER_EXTERNAL_URL supplies the target unless an
    # explicit onrender.com URL is configured.
    render_keepalive_enabled: bool = Field(
        default=False, alias="RENDER_KEEPALIVE_ENABLED"
    )
    render_keepalive_url: str = Field(default="", alias="RENDER_KEEPALIVE_URL")
    render_keepalive_interval_seconds: int = Field(
        default=840,
        alias="RENDER_KEEPALIVE_INTERVAL_SECONDS",
        ge=300,
        le=3600,
    )
    # News video is independently switchable for a quick operational rollback.
    # Existing image news remains available when this is disabled.
    news_video_enabled: bool = Field(default=True, alias="NEWS_VIDEO_ENABLED")
    news_video_max_upload_mb: int = Field(
        default=250, alias="NEWS_VIDEO_MAX_UPLOAD_MB", ge=10, le=1000
    )
    news_youtube_mirroring_enabled: bool = Field(
        default=True, alias="NEWS_YOUTUBE_MIRRORING_ENABLED"
    )

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")  # json or text

    # Google Authentication
    google_client_id: str = Field(
        default="", alias="GOOGLE_CLIENT_ID"
    )  # Firebase Web Client ID
    firebase_project_id: str = Field(
        default="", alias="FIREBASE_PROJECT_ID"
    )  # e.g. multischool-pro
    fcm_service_account_path: str = Field(
        default="", alias="FCM_SERVICE_ACCOUNT_PATH"
    )  # Path to service account JSON
    fcm_service_account_json: str = Field(
        default="", alias="FCM_SERVICE_ACCOUNT_JSON"
    )  # Inline service account JSON for fileless cloud runtimes

    # DeepSeek API (AI Chat) - SECURITY: Must be set via environment variable
    deepseek_api_key: str = Field(alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL"
    )
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")

    # Telegram MTProto API credentials (from my.telegram.org → API development tools)
    # Leave as 0 / empty until you fill in real values from my.telegram.org
    telegram_api_id: Optional[int] = Field(default=None, alias="TELEGRAM_API_ID")
    telegram_api_hash: Optional[str] = Field(default=None, alias="TELEGRAM_API_HASH")

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def coerce_telegram_api_id(cls, v):
        """Allow placeholder strings — return None instead of crashing."""
        if v is None or v == "" or str(v).strip() in ("0", "YOUR_API_ID_HERE", "None", "null"):
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("telegram_api_hash", mode="before")
    @classmethod
    def coerce_telegram_api_hash(cls, v):
        """Treat placeholder strings as unconfigured."""
        if v is None or str(v).strip() in ("", "YOUR_API_HASH_HERE", "None", "null"):
            return None
        return v

    @property
    def legal_app_name(self) -> str:
        """School/app name shown on /privacy and /terms pages."""
        explicit = (self.app_display_name or "").strip()
        if explicit:
            return explicit
        name = (self.app_name or "").strip()
        if name.lower().endswith(" api"):
            return name[:-4].strip() or "School App"
        return name or "School App"

    @property
    def mobile_app_title(self) -> str:
        """Short brand used on leave/form open pages (e.g. PAMAIS / LAS)."""
        short = (self.mobile_app_short_name or "").strip()
        if short:
            return short
        return self.legal_app_name

    @property
    def play_store_url(self) -> str:
        return (
            "https://play.google.com/store/apps/details?"
            f"id={self.android_application_id}"
        )

    @property
    def app_store_url(self) -> str:
        store_id = (self.ios_app_store_id or "").strip()
        if not store_id:
            return ""
        slug = (self.ios_app_store_slug or "").strip()
        if slug:
            return f"https://apps.apple.com/app/{slug}/id{store_id}"
        return f"https://apps.apple.com/app/id{store_id}"

    @property
    def ios_app_id_for_association(self) -> str:
        return f"{self.ios_team_id}.{self.ios_bundle_id}"

    @property
    def android_sha256_list(self) -> list[str]:
        raw = self.android_sha256_cert_fingerprints or ""
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    model_config = SettingsConfigDict(
        env_file="config/.env", env_prefix="", extra="ignore"
    )


# Create settings instance
settings = Settings()
