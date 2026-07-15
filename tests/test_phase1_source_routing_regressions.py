from __future__ import annotations

import pytest

from app.graph import nodes
from app.graph.response_composer import compose_card_summary_reply
from app.graph.search_contracts import SearchStatus


@pytest.mark.parametrize(
    ("message", "request_kind"),
    [
        ("취업지원 정책에 대해 알아보고 싶어", "youth_policy"),
        ("서울에서 개발 교육 정보를 알아보고 싶어", "training"),
    ],
)
async def test_route_validator_does_not_downgrade_valid_llm_search_when_heuristic_is_general(
    message: str,
    request_kind: str,
) -> None:
    """A weak heuristic must not overrule a structurally valid in-scope LLM route."""

    result = await nodes.route_validator_node(
        {
            "user_input": message,
            "intent": "RECOMMEND",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": request_kind,
            "routing_source": "llm",
        }
    )

    assert result == {"route_validation_status": "passed", "route_validation_errors": []}


@pytest.mark.parametrize(
    ("message", "request_kind"),
    [
        ("청년 직업훈련 지원 정책 찾아줘", "youth_policy"),
        ("청년 취업지원 정책 찾아줘", "youth_policy"),
    ],
)
async def test_route_validator_keeps_support_policy_on_youth_center(
    message: str,
    request_kind: str,
) -> None:
    result = await nodes.route_validator_node(
        {
            "user_input": message,
            "intent": "RECOMMEND",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": request_kind,
            "routing_source": "llm",
        }
    )

    assert result == {"route_validation_status": "passed", "route_validation_errors": []}


@pytest.mark.parametrize(
    ("message", "expected_source"),
    [
        ("서울 데이터 분석 국비과정 찾아줘", "training"),
        ("서울에서 지금 채용 중인 회사 공고 찾아줘", "recruitment"),
    ],
)
async def test_route_validator_corrects_concrete_resource_to_work24_source(
    message: str,
    expected_source: str,
) -> None:
    result = await nodes.route_validator_node(
        {
            "user_input": message,
            "intent": "RECOMMEND",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "youth_policy",
            "routing_source": "llm",
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["explicit_source_misclassified"]
    assert result["request_kind"] == expected_source


def test_card_summary_offers_companion_training_search_without_repeating_card_details() -> None:
    response = compose_card_summary_reply(
        request_kind="youth_policy",
        source_status=SearchStatus.SUCCESS,
        candidates=[
            {
                "title": "서울 청년 직업훈련 지원정책",
                "detail_url": "https://example.com/policy/1",
            }
        ],
        companion_sources=["training"],
    )

    assert "카드 1건" in response
    assert "고용24" in response
    assert "훈련과정" in response
    assert "원하시면" in response
    assert "서울 청년 직업훈련 지원정책" not in response
    assert "https://" not in response


def test_card_summary_omits_companion_cta_when_no_companion_is_requested() -> None:
    response = compose_card_summary_reply(
        request_kind="youth_policy",
        source_status=SearchStatus.SUCCESS,
        candidates=[{"title": "서울 청년 주거정책"}],
    )

    assert "카드 1건" in response
    assert "원하시면" not in response
