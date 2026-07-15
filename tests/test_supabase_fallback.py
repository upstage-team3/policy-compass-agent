from __future__ import annotations

from types import SimpleNamespace

from app.repositories.supabase_fallback import _row_to_youth_policy_item
from app.repositories.work24_recruitment import Work24RecruitmentRepository
from app.tools.schemas import RecruitmentInfoItem, RecruitmentInfoSearchInput
from data.scripts.ingest_recruitment_infos import _ENDPOINTS


class _RecruitmentCacheSpy:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: RecruitmentInfoSearchInput) -> list[RecruitmentInfoItem]:
        self.calls += 1
        return [
            RecruitmentInfoItem(
                item_id="cached-1",
                item_type="event",
                title="캐시 채용행사",
                region=query.preferred_work_region,
            )
        ]


def _recruitment_settings() -> SimpleNamespace:
    return SimpleNamespace(
        employment24_job_api_key="test-key",
        employment24_open_recruitment_api_url="https://example.com/open",
        employment24_job_event_api_url="https://example.com/event",
        source_http_timeout_seconds=1.0,
    )


async def test_recruitment_live_no_match_does_not_use_stale_cache(monkeypatch):
    fallback = _RecruitmentCacheSpy()
    repository = Work24RecruitmentRepository(fallback)
    repository._settings = _recruitment_settings()

    async def empty_fetch(*args, **kwargs):
        del args, kwargs
        return []

    monkeypatch.setattr(repository, "_fetch", empty_fetch)

    result = await repository.search(RecruitmentInfoSearchInput(keywords="데이터"))

    assert fallback.calls == 0
    assert len(result) == 1
    assert result[0].item_type == "guide"
    assert "결과 없음" in (result[0].fallback_reason or "")


async def test_recruitment_uses_cache_only_when_all_live_endpoints_fail(monkeypatch):
    fallback = _RecruitmentCacheSpy()
    repository = Work24RecruitmentRepository(fallback)
    repository._settings = _recruitment_settings()

    async def failed_fetch(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(repository, "_fetch", failed_fetch)

    result = await repository.search(RecruitmentInfoSearchInput(preferred_work_region="서울"))

    assert fallback.calls == 1
    assert [item.item_id for item in result] == ["cached-1"]


def test_cached_youth_policy_preserves_age_evidence_fields():
    item = _row_to_youth_policy_item(
        {
            "source": "youthcenter",
            "policy_id": "P1",
            "title": "청년 지원정책",
            "min_age": 19,
            "max_age": 34,
            "age_restricted": True,
        }
    )

    assert item.min_age == 19
    assert item.max_age == 34
    assert item.age_restricted is True


def test_recruitment_cache_ingest_uses_only_supported_endpoints():
    assert _ENDPOINTS == (
        ("open_recruitment", "공채속보", "employment24_open_recruitment_api_url"),
        ("event", "채용행사", "employment24_job_event_api_url"),
    )
