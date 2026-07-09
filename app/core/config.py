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

    # 기업마당 Open API - 미설정 시 data/mock_policies.json 사용
    bizinfo_api_key: str | None = None
    bizinfo_base_url: str = Field(
        default="https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do",
        validation_alias=AliasChoices("BIZINFO_BASE_URL", "BIZINFO_API_URL"),
    )
    use_mock_policy_data: bool = True

    data_dir: Path = BASE_DIR / "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
