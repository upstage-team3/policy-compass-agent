"""LangGraph 노드 구현.

각 노드는 가능하면 Upstage Solar LLM을 사용하고, API 키가 없거나 호출이
실패하면 규칙 기반 휴리스틱으로 안전하게 폴백한다 (LLM 미설정 상태에서도
데모/테스트가 항상 동작하도록 하기 위함).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.llm import LLMUnavailableError, SolarLLMClient, extract_json
from app.core.prompts import (
    GENERAL_REPLY,
    MISSING_SLOT_LABELS,
    OUT_OF_SCOPE_REPLY,
    PROFILE_EXTRACTION_SYSTEM_PROMPT,
    RESPONSE_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
)
from app.graph.scoring import score_policy
from app.graph.state import AgentState
from app.repositories.policy import PolicyRepository
from app.tools.executor import PolicySearchTool
from app.tools.schemas import PolicySearchInput

logger = logging.getLogger(__name__)

_llm = SolarLLMClient()
_policy_repo = PolicyRepository()
_search_tool = PolicySearchTool(_policy_repo)

_REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

_VALID_INTENTS = {"RECOMMEND", "EXPLAIN", "ELIGIBILITY_CHECK", "GENERAL", "OUT_OF_SCOPE"}

_ENTREPRENEUR_KEYWORDS = ["창업", "스타트업", "사업을 시작", "사업 시작"]
_JOB_SEEKING_KEYWORDS = ["구직", "취업 준비", "미취업", "취업활동", "일자리"]
_EMPLOYED_KEYWORDS = ["재직", "직장인", "다니고 있"]
_STUDENT_KEYWORDS = ["대학생", "재학"]
_OUT_OF_SCOPE_KEYWORDS = ["세무 상담", "법률 자문", "소송", "대출 상담", "회계 처리", "변호사"]
_EXPLAIN_KEYWORDS = ["무엇인가요", "뭐야", "설명해", "어떤 내용", "무슨 사업"]
_ELIGIBILITY_KEYWORDS = [
    "자격 되나요",
    "신청 가능한가요",
    "받을 수 있나요",
    "해당되나요",
    "자격이 되는지",
]
_RECOMMEND_KEYWORDS = [
    "추천",
    "지원사업",
    "지원금",
    "정책",
    "받을 수 있는",
    "찾아줘",
    "있을까",
    "있어",
]

_INTEREST_KEYWORDS = {
    "IT": ["IT", "개발", "프로그래밍", "소프트웨어", "앱"],
    "요식업": ["요식업", "카페", "음식점", "식당"],
    "제조업": ["제조업", "제조", "공장"],
    "디자인": ["디자인"],
    "콘텐츠": ["콘텐츠", "영상", "크리에이터"],
    "농업": ["농업", "귀농"],
}


# ---------------------------------------------------------------------------
# Router Node
# ---------------------------------------------------------------------------


async def router_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]
    intent = None

    if _llm.is_configured:
        try:
            raw = await _llm.complete(
                [
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                response_format_json=True,
            )
            intent = extract_json(raw).get("intent")
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 라우터 휴리스틱을 사용합니다.")
        except Exception:  # noqa: BLE001 - LLM 실패 시 휴리스틱으로 안전하게 폴백
            logger.exception("라우터 LLM 호출 실패, 휴리스틱으로 폴백합니다.")

    if intent not in _VALID_INTENTS:
        intent = _heuristic_route(user_input)

    return {"intent": intent}


def _heuristic_route(text: str) -> str:
    if any(k in text for k in _OUT_OF_SCOPE_KEYWORDS):
        return "OUT_OF_SCOPE"
    if any(k in text for k in _ELIGIBILITY_KEYWORDS):
        return "ELIGIBILITY_CHECK"
    if any(k in text for k in _EXPLAIN_KEYWORDS):
        return "EXPLAIN"
    if any(k in text for k in _RECOMMEND_KEYWORDS) or any(
        k in text for k in _JOB_SEEKING_KEYWORDS + _ENTREPRENEUR_KEYWORDS
    ):
        return "RECOMMEND"
    return "GENERAL"


# ---------------------------------------------------------------------------
# Profile Extractor Node
# ---------------------------------------------------------------------------


async def profile_extractor_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]
    previous_profile = dict(state.get("profile") or {})

    extracted: dict[str, Any] = {}
    if _llm.is_configured:
        try:
            raw = await _llm.complete(
                [
                    {"role": "system", "content": PROFILE_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                response_format_json=True,
            )
            extracted = extract_json(raw)
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 프로필 추출 휴리스틱을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("프로필 추출 LLM 호출 실패, 휴리스틱으로 폴백합니다.")

    if not extracted:
        extracted = _heuristic_extract_profile(user_input)

    merged = {**previous_profile}
    for key, value in extracted.items():
        if value in (None, "", []):
            continue
        if key == "interest_fields":
            merged[key] = sorted(set(merged.get("interest_fields", []) + list(value)))
        else:
            merged[key] = value

    return {"profile": merged}


def _heuristic_extract_profile(text: str) -> dict[str, Any]:
    profile: dict[str, Any] = {}

    age_match = re.search(r"(\d{2})\s*살|(\d{2})\s*세", text)
    if age_match:
        profile["age"] = int(next(g for g in age_match.groups() if g))

    for region in _REGIONS:
        if region in text:
            profile["region"] = region
            break

    if any(k in text for k in _JOB_SEEKING_KEYWORDS):
        profile["employment_status"] = "unemployed_seeking_job"
    elif any(k in text for k in _EMPLOYED_KEYWORDS):
        profile["employment_status"] = "employed"
    elif any(k in text for k in _STUDENT_KEYWORDS):
        profile["employment_status"] = "student"

    if "졸업 예정" in text or "졸업예정" in text:
        profile["graduation_status"] = "expected_graduate"
    elif "재학" in text:
        profile["graduation_status"] = "enrolled"
    elif "졸업" in text:
        months_match = re.search(r"졸업.{0,6}?(\d+)\s*개월", text)
        years_match = re.search(r"졸업.{0,6}?(\d+)\s*년", text)
        if months_match and int(months_match.group(1)) <= 24:
            profile["graduation_status"] = "graduated_within_2y"
        elif years_match and int(years_match.group(1)) <= 2:
            profile["graduation_status"] = "graduated_within_2y"
        elif years_match:
            profile["graduation_status"] = "graduated_over_2y"
        else:
            profile["graduation_status"] = "graduated_within_2y"

    if any(k in text for k in _ENTREPRENEUR_KEYWORDS):
        profile["is_entrepreneur"] = True

    if "사업자 등록" in text:
        profile["has_registered_business"] = not any(
            neg in text for neg in ["안 했", "안했", "없", "아직", "미등록"]
        )

    matched_fields = [
        field for field, kws in _INTEREST_KEYWORDS.items() if any(k in text for k in kws)
    ]
    if matched_fields:
        profile["interest_fields"] = matched_fields

    return profile


# ---------------------------------------------------------------------------
# Missing Slot Node
# ---------------------------------------------------------------------------


async def missing_slot_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    missing: list[str] = []

    if not profile.get("region"):
        missing.append("region")
    if profile.get("employment_status") is None and profile.get("is_entrepreneur") is None:
        missing.append("status")

    return {"missing_slots": missing}


async def clarification_node(state: AgentState) -> dict[str, Any]:
    missing = state.get("missing_slots", [])
    labels = [MISSING_SLOT_LABELS.get(slot, slot) for slot in missing]
    question = "맞춤 추천을 위해 몇 가지만 더 확인할게요! " + ", ".join(labels) + " 알려주시겠어요?"
    return {"final_response": question, "search_results": [], "scored_results": []}


# ---------------------------------------------------------------------------
# Policy Search + Eligibility Scorer Nodes
# ---------------------------------------------------------------------------


async def policy_search_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    search_input = PolicySearchInput(
        region=profile.get("region"),
        employment_status=profile.get("employment_status"),
        is_entrepreneur=profile.get("is_entrepreneur"),
        has_registered_business=profile.get("has_registered_business"),
        interest_fields=profile.get("interest_fields", []),
        keywords=state["user_input"],
    )
    results = await _search_tool.execute(search_input)
    return {"search_results": [r.model_dump() for r in results]}


async def eligibility_scorer_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    scored = [score_policy(profile, policy) for policy in state.get("search_results", [])]
    scored.sort(key=lambda item: item["match_score"], reverse=True)
    return {"scored_results": scored[:5]}


# ---------------------------------------------------------------------------
# Response Node
# ---------------------------------------------------------------------------


async def response_node(state: AgentState) -> dict[str, Any]:
    scored = state.get("scored_results", [])
    profile = state.get("profile") or {}

    if not scored:
        text = (
            "입력하신 조건에 맞는 지원사업을 찾지 못했어요. 관심 분야나 지역을 조금 더 "
            "알려주시면 다시 찾아볼게요."
        )
        return {"final_response": text}

    if _llm.is_configured:
        try:
            text = await _compose_with_llm(profile, scored)
            return {"final_response": text}
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 응답 생성 휴리스틱을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("응답 생성 LLM 호출 실패, 템플릿으로 폴백합니다.")

    return {"final_response": _compose_with_template(scored)}


async def _compose_with_llm(profile: dict, scored: list[dict]) -> str:
    payload = {"profile": profile, "candidates": scored}
    return await _llm.complete(
        [
            {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.4,
    )


def _compose_with_template(scored: list[dict]) -> str:
    lines = ["조건을 바탕으로 확인해볼 만한 지원사업을 정리했어요."]
    for idx, item in enumerate(scored, start=1):
        policy = item["policy"]
        lines.append("")
        lines.append(f"{idx}. {policy['title']} ({policy['agency']})")
        lines.append(f"   - 지원 대상: {policy['target_description']}")
        lines.append(f"   - 지원 내용: {policy['support_content']}")
        lines.append(
            "   - 신청 기간: "
            f"{policy.get('apply_start') or '상시'} ~ {policy.get('apply_end') or '상시'} "
            f"[{item['deadline_status']}]"
        )
        lines.append(f"   - 신청 방법: {policy['apply_method']}")
        lines.append(f"   - 추천 이유: {' '.join(item['match_reasons'])}")
        if item["follow_up_checks"]:
            lines.append(f"   - 신청 전 확인 필요: {' '.join(item['follow_up_checks'])}")
        lines.append(f"   - 원문 링크: {policy['source_url']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Explain / General / Out-of-scope Nodes
# ---------------------------------------------------------------------------


async def explain_node(state: AgentState) -> dict[str, Any]:
    query = state["user_input"]
    policy = await _policy_repo.find_best_title_match(query)
    if not policy:
        return {
            "final_response": (
                "어떤 지원사업에 대해 설명이 필요하신지 "
                "사업명을 조금 더 구체적으로 알려주시겠어요?"
            )
        }
    text = (
        f"'{policy['title']}'({policy['agency']}) 안내드릴게요.\n"
        f"- 지원 대상: {policy['target_description']}\n"
        f"- 지원 내용: {policy['support_content']}\n"
        "- 신청 기간: "
        f"{policy.get('apply_start') or '상시'} ~ {policy.get('apply_end') or '상시'}\n"
        f"- 신청 방법: {policy['apply_method']}\n"
        f"- 원문 링크: {policy['source_url']}"
    )
    return {"final_response": text}


async def general_node(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
    return {"final_response": GENERAL_REPLY}


async def out_of_scope_node(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
    return {"final_response": OUT_OF_SCOPE_REPLY}


# ---------------------------------------------------------------------------
# Guardrail Node
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS = [
    (re.compile(r"반드시\s*(신청|지원)\s*가능(합니다|해요)?"), "신청 가능성이 높아요"),
    (
        re.compile(r"무조건\s*(지원|선정)?\s*(됩니다|돼요|가능합니다)?"),
        "높은 확률로 도움이 될 수 있어요",
    ),
    (re.compile(r"100\s*%\s*(확실|가능)"), "가능성이 높지만 추가 확인이 필요"),
]

_DISCLAIMER = (
    "\n\n※ 최종 자격 및 신청 가능 여부는 공식 공고문 또는 담당 기관을 통해 꼭 확인해주세요."
)


async def guardrail_node(state: AgentState) -> dict[str, Any]:
    text = state.get("final_response", "")
    notes: list[str] = []

    for pattern, replacement in _FORBIDDEN_PATTERNS:
        if pattern.search(text):
            text = pattern.sub(replacement, text)
            notes.append("확정적 표현을 완화된 표현으로 수정했습니다.")

    if state.get("scored_results") and _DISCLAIMER.strip() not in text:
        text = text + _DISCLAIMER

    return {"final_response": text, "guardrail_notes": notes}
