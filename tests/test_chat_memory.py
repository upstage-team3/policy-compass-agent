import httpx

from app.repositories.chat_memory import SupabaseChatMemoryRepository, _safe_content


def test_safe_content_masks_sensitive_identifiers_and_limits_length():
    content = "주민번호 900101-1234567 카드 1234-5678-9012-3456 " + ("가" * 5000)

    sanitized = _safe_content(content)

    assert "900101-1234567" not in sanitized
    assert "1234-5678-9012-3456" not in sanitized
    assert "[민감정보 삭제]" in sanitized
    assert len(sanitized) <= 4000


async def test_local_memory_preserves_multiturn_state_without_supabase():
    repository = SupabaseChatMemoryRepository()
    repository._base_url = ""
    repository._key = ""

    await repository.save_turn(
        session_id="local-session",
        user_message="서울에 살아",
        assistant_message="지역을 저장했어요",
        intent="GENERAL",
        profile={"region": "서울"},
        pending_request={"required_slots": ["age"]},
        last_presented_candidates=[{"source": "training", "title": "데이터 과정"}],
    )
    await repository.save_turn(
        session_id="local-session",
        user_message="만 25세야",
        assistant_message="확인했어요",
        intent="RECOMMEND",
        profile={"region": "서울", "age": 25},
        pending_request={},
    )

    context = await repository.load("local-session")

    assert context.profile == {"region": "서울", "age": 25}
    assert context.pending_request == {}
    assert context.last_presented_candidates == [{"source": "training", "title": "데이터 과정"}]
    assert [message["content"] for message in context.messages] == [
        "서울에 살아",
        "지역을 저장했어요",
        "만 25세야",
        "확인했어요",
    ]


async def test_local_memory_preserves_completed_search_plan_without_candidates():
    repository = SupabaseChatMemoryRepository()
    repository._base_url = ""
    repository._key = ""
    plan = {
        "request_kind": "recruitment",
        "response_mode": "recommend",
        "search_query": "데이터 분석",
        "effective_filters": {"work_region": "서울", "region_mode": "specific"},
        "source_status": "no_match",
    }

    await repository.save_turn(
        session_id="last-plan-session",
        user_message="서울 데이터 채용을 찾아줘",
        assistant_message="결과가 없어요.",
        intent="RECOMMEND",
        profile={"region": "서울"},
        pending_request={},
        last_presented_candidates=[],
        last_search_plan=plan,
    )
    await repository.save_turn(
        session_id="last-plan-session",
        user_message="고마워",
        assistant_message="별말씀을요.",
        intent="GENERAL",
        profile={"region": "서울"},
        pending_request={},
    )

    context = await repository.load("last-plan-session")
    assert context.last_presented_candidates == []
    assert context.last_search_plan == plan


async def test_local_memory_returns_a_copy_and_can_be_cleared():
    repository = SupabaseChatMemoryRepository()
    repository._base_url = ""
    repository._key = ""
    await repository.save_turn(
        session_id="copy-session",
        user_message="질문",
        assistant_message="답변",
        intent="GENERAL",
        profile={"region": "부산"},
        pending_request={},
    )

    first = await repository.load("copy-session")
    first.profile["region"] = "변조"
    second = await repository.load("copy-session")
    assert second.profile["region"] == "부산"

    await repository.clear_local()
    assert await repository.load("copy-session") == type(second)()


async def test_failed_remote_save_keeps_newer_local_state_on_next_load(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):  # noqa: ARG002
            return httpx.Response(503, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.repositories.chat_memory.httpx.AsyncClient", FailingClient)
    repository = SupabaseChatMemoryRepository()
    repository._base_url = "https://supabase.example"
    repository._key = "test-key"

    await repository.save_turn(
        session_id="dirty-session",
        user_message="나이는 저장하지 마",
        assistant_message="삭제했어요",
        intent="GENERAL",
        profile={},
        pending_request={},
        last_presented_candidates=[],
    )

    class UnexpectedRemoteClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("dirty local state must not be overwritten by stale remote data")

    monkeypatch.setattr("app.repositories.chat_memory.httpx.AsyncClient", UnexpectedRemoteClient)
    context = await repository.load("dirty-session")

    assert context.profile == {}
    assert context.pending_request == {}
    assert context.last_presented_candidates == []
    assert context.messages[-1]["content"] == "삭제했어요"


async def test_dirty_local_authority_survives_a_later_successful_append(monkeypatch):
    class ToggleClient:
        should_fail = True

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):  # noqa: ARG002
            status = 503 if self.should_fail else 201
            return httpx.Response(status, request=httpx.Request("POST", url))

        async def get(self, url, **kwargs):  # noqa: ARG002
            raise AssertionError("dirty local history must remain authoritative")

    monkeypatch.setattr("app.repositories.chat_memory.httpx.AsyncClient", ToggleClient)
    repository = SupabaseChatMemoryRepository()
    repository._base_url = "https://supabase.example"
    repository._key = "test-key"

    await repository.save_turn(
        session_id="persistently-dirty",
        user_message="첫 대화",
        assistant_message="첫 답변",
        intent="GENERAL",
        profile={"region": "서울"},
        pending_request={},
    )
    ToggleClient.should_fail = False
    await repository.save_turn(
        session_id="persistently-dirty",
        user_message="둘째 대화",
        assistant_message="둘째 답변",
        intent="GENERAL",
        profile={"region": "서울"},
        pending_request={},
    )

    context = await repository.load("persistently-dirty")
    assert [message["content"] for message in context.messages] == ["첫 대화", "첫 답변", "둘째 대화", "둘째 답변"]


async def test_legacy_session_load_recovers_candidate_snapshot_from_pending_json(monkeypatch):
    class LegacyLoadClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            request = httpx.Request("GET", url)
            if url.endswith("/chat_logs"):
                return httpx.Response(200, json=[], request=request)
            if "last_presented_candidates" in kwargs["params"]["select"]:
                return httpx.Response(400, request=request)
            return httpx.Response(
                200,
                json=[
                    {
                        "profile": {"region": "서울"},
                        "pending_request": {
                            "required_slots": ["age"],
                            "__policy_compass_candidates_v1": [{"source": "training", "title": "데이터 과정"}],
                        },
                    }
                ],
                request=request,
            )

    monkeypatch.setattr("app.repositories.chat_memory.httpx.AsyncClient", LegacyLoadClient)
    repository = SupabaseChatMemoryRepository()
    repository._base_url = "https://supabase.example"
    repository._key = "test-key"

    context = await repository.load("legacy-session")

    assert context.profile == {"region": "서울"}
    assert context.pending_request == {"required_slots": ["age"]}
    assert context.last_presented_candidates == [{"source": "training", "title": "데이터 과정"}]


async def test_legacy_session_save_embeds_candidate_snapshot_in_pending_json(monkeypatch):
    legacy_session_payloads: list[dict] = []

    class LegacySaveClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            request = httpx.Request("POST", url)
            payload = kwargs.get("json")
            if url.endswith("/chat_logs"):
                return httpx.Response(201, request=request)
            if isinstance(payload, dict) and "last_presented_candidates" in payload:
                return httpx.Response(400, request=request)
            legacy_session_payloads.append(payload)
            return httpx.Response(201, request=request)

    monkeypatch.setattr("app.repositories.chat_memory.httpx.AsyncClient", LegacySaveClient)
    repository = SupabaseChatMemoryRepository()
    repository._base_url = "https://supabase.example"
    repository._key = "test-key"

    await repository.save_turn(
        session_id="legacy-session",
        user_message="과정 찾아줘",
        assistant_message="카드를 확인해 주세요",
        intent="RECOMMEND",
        profile={"region": "서울"},
        pending_request={"required_slots": ["age"]},
        last_presented_candidates=[{"source": "training", "title": "데이터 과정"}],
    )

    assert len(legacy_session_payloads) == 1
    stored_pending = legacy_session_payloads[0]["pending_request"]
    assert stored_pending["required_slots"] == ["age"]
    assert stored_pending["__policy_compass_candidates_v1"] == [{"source": "training", "title": "데이터 과정"}]
