"""고용24 국민내일배움카드 훈련과정을 API로 가져와 Supabase training_courses 테이블에 저장하는 배치 스크립트.

Work24TrainingRepository.search()를 거치지 않고 API 호출 + 정규화 함수를 직접
사용한다 (search()는 실패/빈 결과 시 안내용 합성 레코드를 반환하는데, 그건 실제
훈련과정이 아니라 DB에 저장할 대상이 아니다).

실행: uv run python data/scripts/ingest_training_courses.py
필요 환경변수: EMPLOYMENT24_TRAINING_API_KEY, SUPABASE_URL, SUPABASE_KEY
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import Settings, get_settings  # noqa: E402
from app.repositories.work24_training import (  # noqa: E402
    default_training_period,
    normalize_training_courses,
)
from app.tools.schemas import TrainingCourseItem  # noqa: E402

PAGE_SIZE = 100
MAX_PAGES = 20  # 안전장치: 페이지네이션이 예상과 다르게 동작해도 무한 호출 방지


def fetch_all_courses(settings: Settings) -> list[TrainingCourseItem]:
    start, end = default_training_period()
    courses: list[TrainingCourseItem] = []

    with httpx.Client(timeout=15) as client:
        for page in range(1, MAX_PAGES + 1):
            params = {
                "authKey": settings.employment24_training_api_key,
                "returnType": "XML",
                "outType": "1",
                "pageNum": str(page),
                "pageSize": str(PAGE_SIZE),
                "srchTraStDt": start,
                "srchTraEndDt": end,
                "sort": "ASC",
                "sortCol": "2",
            }
            response = client.get(settings.employment24_training_api_url, params=params)
            response.raise_for_status()

            try:
                page_items = normalize_training_courses(response.text)
            except ET.ParseError:
                print(f"[ingest_training_courses] {page}페이지 XML 파싱 실패, 중단합니다.")
                break

            if not page_items:
                break
            courses.extend(page_items)
            print(f"[ingest_training_courses] {page}페이지: {len(page_items)}건")
            if len(page_items) < PAGE_SIZE:
                break

    return courses


def to_row(item: TrainingCourseItem, *, fetched_at: str) -> dict[str, Any]:
    row = item.model_dump(exclude={"fallback_reason", "raw"})
    row["raw_payload"] = item.raw
    row["fetched_at"] = fetched_at
    row["updated_at"] = fetched_at
    return row


def upsert_rows(settings: Settings, rows: list[dict[str, Any]]) -> None:
    headers = {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    url = f"{settings.supabase_url}/rest/v1/training_courses"

    with httpx.Client(timeout=30) as client:
        for i in range(0, len(rows), 200):
            batch = rows[i : i + 200]
            response = client.post(url, headers=headers, json=batch)
            response.raise_for_status()
            print(f"[ingest_training_courses] {len(batch)}건 upsert 완료 ({i + len(batch)}/{len(rows)})")


def main() -> None:
    settings = get_settings()

    missing = [
        name
        for name, value in (
            ("EMPLOYMENT24_TRAINING_API_KEY", settings.employment24_training_api_key),
            ("SUPABASE_URL", settings.supabase_url),
            ("SUPABASE_KEY", settings.supabase_key),
        )
        if not value
    ]
    if missing:
        print(f"[ingest_training_courses] 다음 환경변수가 없어 중단합니다: {', '.join(missing)}")
        return

    print("[ingest_training_courses] 고용24 훈련과정 조회 중...")
    items = fetch_all_courses(settings)
    real_items = [item for item in items if not item.fallback_reason]
    print(f"[ingest_training_courses] 총 {len(real_items)}건 조회 완료")

    if not real_items:
        print("[ingest_training_courses] 저장할 데이터가 없어 종료합니다.")
        return

    fetched_at = datetime.now(UTC).isoformat()
    rows = [to_row(item, fetched_at=fetched_at) for item in real_items]
    upsert_rows(settings, rows)
    print(f"[ingest_training_courses] 완료: {len(rows)}건을 training_courses 테이블에 저장했습니다.")


if __name__ == "__main__":
    main()
