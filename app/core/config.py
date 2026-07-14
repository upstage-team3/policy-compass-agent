from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """애플리케이션 설정.

    .env 파일 또는 환경변수에서 값을 읽는다. LLM/외부 API 키가 없어도
    앱이 정상적으로 기동되고, 각 계층에서 규칙 기반 fallback으로
    동작하도록 설계했다 (데모/CI 환경에서도 키 없이 실행 가능).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "정책나침반 (Policy Compass)"
    app_env: str = "local"
    log_level: str = "INFO"

    cors_origins: list[str] = ["*"]

    # LLM (Upstage Solar) - 미설정 시 규칙 기반 휴리스틱으로 자동 폴백
    upstage_api_key: str | None = None
    upstage_base_url: str = "https://api.upstage.ai/v1"
    upstage_model: str = "solar-pro2"

    # 온통청년 청년정책 API
    youthcenter_policy_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("YOUTHCENTER_POLICY_API_KEY", "YOUTHCENTER_API_KEY"),
    )
    youthcenter_policy_api_url: str = Field(
        default="https://www.youthcenter.go.kr/go/ythip/getPlcy",
        validation_alias=AliasChoices("YOUTHCENTER_POLICY_API_URL", "YOUTHCENTER_API_URL"),
    )

    # 고용24/HRD-Net 국민내일배움카드 훈련과정 API
    employment24_training_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMPLOYMENT24_TRAINING_API_KEY", "EMPLOYMENT24_API_KEY"),
    )
    employment24_training_api_url: str = Field(
        default="https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do",
        validation_alias=AliasChoices("EMPLOYMENT24_TRAINING_API_URL"),
    )

    # 고용24 개인회원 허용 API: 채용행사, 공채속보, 공채기업정보
    employment24_job_api_key: str | None = None
    employment24_job_event_api_url: str = Field(
        default="https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L11.do",
        validation_alias=AliasChoices("EMPLOYMENT24_JOB_EVENT_API_URL"),
    )
    employment24_open_recruitment_api_url: str = Field(
        default="https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L21.do",
        validation_alias=AliasChoices("EMPLOYMENT24_OPEN_RECRUITMENT_API_URL"),
    )
    employment24_company_api_url: str = Field(
        default="https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L31.do",
        validation_alias=AliasChoices("EMPLOYMENT24_COMPANY_API_URL"),
    )

    # 기업마당 Open API - API 키가 없거나 호출에 실패하면 빈 결과 반환
    bizinfo_api_key: str | None = None
    bizinfo_base_url: str = Field(
        default="https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do",
        validation_alias=AliasChoices("BIZINFO_BASE_URL", "BIZINFO_API_URL"),
    )

    # Supabase - 대화 메모리와 training_courses fallback 캐시 공용
    supabase_url: str | None = None
    supabase_key: str | None = None

    # Langfuse - 키가 모두 있을 때만 LangGraph tracing 활성화
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_tracing_environment: str = "development"

    data_dir: Path = BASE_DIR / "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
