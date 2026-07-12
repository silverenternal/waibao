from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # 兼容老 env / 多余字段,不报 ValidationError
    )

    # ---- Core ----
    env: str = "development"
    supabase_url: str = "http://localhost:54321"
    supabase_key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # local dev default
    supabase_service_key: str = ""
    supabase_jwt_secret: str = "super-secret-jwt-token-with-at-least-32-characters-long"  # Supabase project JWT secret
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    database_url: str = "postgresql://postgres:postgres@localhost:54322/postgres"
    cors_origins: list[str] = ["http://localhost:3000"]

    # T1203 — WeChat mini-program login
    wechat_appid: str = ""
    wechat_secret: str = ""
    mobile_jwt_enabled: bool = True
    mobile_jwt_secret: str = ""

    # ---- v4.0 — 多区域 / 合规 ----
    region: str = "local"
    data_residency: str = "local"
    default_locale: str = "zh"
    pii_encryption_key: str = ""
    region_routing_primary: str = "local"
    region_routing_replicas: str = ""

    # ---- v4.0 — Third-party ----
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    anthropic_api_key: str = ""
    stripe_secret_key: str = ""
    stripe_secret_key_cn: str = ""
    zoom_api_key: str = ""
    zoom_api_secret: str = ""
    greenhouse_api_key: str = ""
    lever_api_key: str = ""
    checkr_api_key: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_endpoint: str = ""
    oss_bucket: str = ""
    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    # ---- v4.0 — Compliance ----
    gdpr_dpo_contact: str = ""
    ccpa_opt_out_enabled: bool = False
    icp_license: str = ""

    # ---- v4.0 — Observability ----
    sentry_dsn: str = ""
    audit_log_endpoint: str = ""
    rate_limit_per_user: int = 100
    llm_budget_per_user: int = 100000

    # ---- Backwards-compat aliases ----
    @property
    def wechat_miniprogram_appid(self) -> str:
        return self.wechat_appid

    @property
    def wechat_miniprogram_secret(self) -> str:
        return self.wechat_secret


settings = Settings()
