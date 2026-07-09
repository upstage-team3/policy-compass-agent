"""기업마당 Open API에서 정책 공고를 가져와 정규화된 JSON으로 저장하는 배치 스크립트.

BIZINFO_API_KEY 가 설정되지 않았거나 호출에 실패하면, 기존
data/mock_policies.json 을 그대로 유지한다 (MVP 데모 흐름을 끊지 않기 위함).

실행: uv run python data/scripts/ingest_data.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = DATA_DIR / "mock_policies.json"
BIZINFO_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"


def normalize_bizinfo_item(raw: dict) -> dict:
    """기업마당 API 응답 1건을 PolicyItem 스키마 형태로 정규화한다.

    실제 필드명은 기업마당 API 응답 스펙(hashtags/pblancNm/jrsdInsttNm 등)에
    맞춰 조정이 필요하다. 여기서는 대표적인 필드만 매핑하는 최소 구현을 둔다.
    """

    return {
        "id": raw.get("pblancId") or raw.get("id") or "",
        "title": raw.get("pblancNm") or raw.get("title") or "",
        "agency": raw.get("jrsdInsttNm") or raw.get("agency") or "미확인 기관",
        "category": raw.get("pldirSportRealmLclasCodeNm") or "경영/기술",
        "target_description": raw.get("trgetNm") or "",
        "region": [raw.get("area") or "전국"],
        "min_age": None,
        "max_age": None,
        "target_employment_status": [],
        "target_entrepreneur": None,
        "requires_business_registration": None,
        "apply_start": raw.get("reqstBeginEndDe", "").split("~")[0].strip() or None,
        "apply_end": raw.get("reqstBeginEndDe", "").split("~")[-1].strip() or None,
        "apply_method": raw.get("reqstMthPapersCn") or "공고문 참조",
        "support_content": raw.get("pldirSportCn") or "",
        "source_url": raw.get("pblancUrl") or "https://www.bizinfo.go.kr/",
    }


def fetch_bizinfo(api_key: str) -> list[dict] | None:
    try:
        response = httpx.get(
            BIZINFO_URL,
            params={"crtfcKey": api_key, "dataType": "json"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[ingest_data] 기업마당 API 호출 실패: {exc}", file=sys.stderr)
        return None

    items = payload.get("jsonArray") or payload.get("items") or []
    if not items:
        print("[ingest_data] 기업마당 API 응답에 항목이 없습니다.", file=sys.stderr)
        return None

    return [normalize_bizinfo_item(item) for item in items]


def main() -> None:
    api_key = os.getenv("BIZINFO_API_KEY")
    if not api_key:
        print(
            "[ingest_data] BIZINFO_API_KEY 가 설정되지 않아 mock_policies.json 을 그대로 유지합니다."
        )
        return

    normalized = fetch_bizinfo(api_key)
    if not normalized:
        print("[ingest_data] 정규화된 데이터가 없어 기존 mock 데이터를 유지합니다.")
        return

    OUTPUT_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ingest_data] {len(normalized)}건의 정책 데이터를 {OUTPUT_PATH} 에 저장했습니다.")


if __name__ == "__main__":
    main()
