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

from pydantic import ValidationError

from app.core.llm import LLMUnavailableError, SolarLLMClient, extract_json
from app.core.prompts import (
    MISSING_SLOT_LABELS,
    OUT_OF_SCOPE_REPLY,
    PROFILE_EXTRACTION_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
)
from app.graph.contracts import VALID_REQUEST_KINDS, RoutingDecision
from app.graph.fallbacks import (
    classify_request_kind as _classify_request_kind,
)
from app.graph.fallbacks import (
    extract_training_search_keyword as _extract_training_search_keyword,
)
from app.graph.fallbacks import (
    heuristic_extract_profile as _heuristic_extract_profile,
)
from app.graph.fallbacks import (
    heuristic_route as _heuristic_route,  # noqa: F401 - fallback 테스트 호환용 재노출
)
from app.graph.fallbacks import routing_plan as _fallback_routing_plan
from app.graph.response_composer import (
    compose_conversation_reply,
    compose_grounded_results,
    compose_scored_results,
)
from app.graph.response_composer import (
    compose_recruitment_response as _compose_recruitment_response,
)
from app.graph.response_composer import (
    compose_scored_template as _compose_with_template,
)
from app.graph.response_composer import (
    compose_training_response as _compose_training_response,
)
from app.graph.response_composer import (
    compose_youth_policy_response as _compose_youth_policy_response,
)
from app.graph.scoring import score_policy
from app.graph.state import AgentState
from app.repositories.policy import PolicyRepository
from app.repositories.work24_recruitment import Work24RecruitmentRepository
from app.repositories.work24_training import Work24TrainingRepository
from app.repositories.youthcenter import YouthCenterRepository
from app.tools.executor import (
    PolicySearchTool,
    RecruitmentInfoTool,
    TrainingCourseSearchTool,
    YouthPolicySearchTool,
)
from app.tools.schemas import (
    PolicySearchInput,
    RecruitmentInfoSearchInput,
    TrainingCourseSearchInput,
    YouthPolicySearchInput,
)

logger = logging.getLogger(__name__)

_llm = SolarLLMClient()
_policy_repo = PolicyRepository()
_search_tool = PolicySearchTool(_policy_repo)
_youth_policy_tool = YouthPolicySearchTool(YouthCenterRepository(_policy_repo))
_training_tool = TrainingCourseSearchTool(Work24TrainingRepository())
_recruitment_tool = RecruitmentInfoTool(Work24RecruitmentRepository())

# ---------------------------------------------------------------------------
# Router Node
# ---------------------------------------------------------------------------


async def router_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]
    action = None
    response_mode = None
    intent = None
    request_kind = None
    search_query = None
    routing_source = "heuristic"

    if _llm.is_configured:
        try:
            routing_context = {
                "message": user_input,
                "known_profile": state.get("profile") or {},
            }
            raw = await _llm.complete(
                [
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(routing_context, ensure_ascii=False)},
                ],
                response_format_json=True,
            )
            decision = RoutingDecision.model_validate(extract_json(raw))
            action = decision.action.value
            response_mode = decision.response_mode.value
            intent = decision.intent.value
            request_kind = decision.request_kind.value
            search_query = decision.search_query
            routing_source = "llm"
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 라우터 휴리스틱을 사용합니다.")
        except ValidationError as exc:
            logger.warning("라우터 LLM 응답 계약 검증 실패, 휴리스틱으로 폴백합니다: %s", exc.errors())
        except Exception:  # noqa: BLE001 - LLM 실패 시 휴리스틱으로 안전하게 폴백
            logger.exception("라우터 LLM 호출 실패, 휴리스틱으로 폴백합니다.")

    if action is None:
        fallback = _fallback_routing_plan(user_input, state.get("profile"))
        action = fallback["action"]
        response_mode = fallback["response_mode"]
        intent = fallback["intent"]
        request_kind = fallback["request_kind"]
        search_query = fallback["search_query"]
        routing_source = "heuristic"

    logger.info(
        "routing_decision source=%s action=%s mode=%s request_kind=%s has_search_query=%s",
        routing_source,
        action,
        response_mode,
        request_kind,
        bool(search_query),
    )

    return {
        "intent": intent,
        "action": action,
        "response_mode": response_mode,
        "request_kind": request_kind,
        "search_query": search_query,
        "routing_source": routing_source,
    }


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

    request_kind = state.get("request_kind")
    if request_kind not in VALID_REQUEST_KINDS or request_kind == "general":
        request_kind = _classify_request_kind(user_input, merged)
    merged["request_kind"] = request_kind

    return {"profile": merged, "request_kind": request_kind}


# ---------------------------------------------------------------------------
# Missing Slot Node
# ---------------------------------------------------------------------------


async def missing_slot_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    request_kind = state.get("request_kind") or profile.get("request_kind") or "youth_policy"
    missing: list[str] = []

    if state.get("response_mode") == "explain":
        return {"missing_slots": []}

    if request_kind == "training":
        if not state.get("search_query") and not profile.get("desired_job") and not profile.get("interest_fields"):
            missing.append("desired_job")
        if not profile.get("region"):
            missing.append("training_region")
    elif request_kind == "recruitment":
        # 채용정보목록/상세는 개인키 제한 안내가 핵심이므로, 조건이 부족해도
        # 먼저 탐색 가이드를 제공하고 이후 직무/지역을 보완하도록 한다.
        missing = []
    else:
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
    request_kind = state.get("request_kind") or profile.get("request_kind") or "youth_policy"
    planned_query = state.get("search_query")

    if request_kind == "training":
        desired_job = (
            planned_query
            or profile.get("desired_job")
            or _extract_training_search_keyword(state["user_input"])
            or " ".join(profile.get("interest_fields") or [])
            or state["user_input"]
        )
        training_input = TrainingCourseSearchInput(
            desired_job=desired_job,
            training_region=profile.get("region"),
            keywords=state["user_input"],
        )
        results = await _training_tool.execute(training_input)
        return {
            "search_results": [],
            "youth_policy_results": [],
            "training_results": [item.model_dump() for item in results],
            "recruitment_results": [],
        }

    if request_kind == "recruitment":
        recruitment_input = RecruitmentInfoSearchInput(
            desired_job=planned_query or profile.get("desired_job"),
            preferred_work_region=profile.get("region"),
            keywords=planned_query or state["user_input"],
        )
        results = await _recruitment_tool.execute(recruitment_input)
        return {
            "search_results": [],
            "youth_policy_results": [],
            "training_results": [],
            "recruitment_results": [item.model_dump() for item in results],
        }

    search_input = PolicySearchInput(
        region=profile.get("region"),
        age=profile.get("age"),
        employment_status=profile.get("employment_status"),
        graduation_status=profile.get("graduation_status"),
        is_entrepreneur=profile.get("is_entrepreneur"),
        has_registered_business=profile.get("has_registered_business"),
        desired_job=profile.get("desired_job"),
        preferred_support_type=profile.get("preferred_support_type"),
        interest_fields=profile.get("interest_fields", []),
        keywords=planned_query or state["user_input"],
    )
    youth_input = YouthPolicySearchInput(
        region=profile.get("region"),
        age=profile.get("age"),
        employment_status=profile.get("employment_status"),
        graduation_status=profile.get("graduation_status"),
        support_types=[profile["preferred_support_type"]] if profile.get("preferred_support_type") else [],
        interest_fields=profile.get("interest_fields", []),
        keywords=planned_query or state["user_input"],
    )
    if request_kind == "business":
        results = await _search_tool.execute(search_input)
        youth_results = []
    else:
        results = []
        youth_results = await _youth_policy_tool.execute(youth_input)
    return {
        "search_results": [r.model_dump() for r in results],
        "youth_policy_results": [item.model_dump() for item in youth_results],
        "training_results": [],
        "recruitment_results": [],
    }


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
    youth_policies = state.get("youth_policy_results", [])
    training_courses = state.get("training_results", [])
    recruitment_items = state.get("recruitment_results", [])
    profile = state.get("profile") or {}
    response_mode = state.get("response_mode", "recommend")

    if training_courses:
        generated = await compose_grounded_results(
            _llm,
            user_input=state["user_input"],
            profile=profile,
            source_type="work24_training",
            response_mode=response_mode,
            candidates=training_courses,
        )
        if generated:
            return {"final_response": generated}
        return {"final_response": _compose_training_response(training_courses)}

    if recruitment_items:
        generated = await compose_grounded_results(
            _llm,
            user_input=state["user_input"],
            profile=profile,
            source_type="work24_recruitment",
            response_mode=response_mode,
            candidates=recruitment_items,
        )
        if generated:
            return {"final_response": generated}
        return {"final_response": _compose_recruitment_response(recruitment_items)}

    if youth_policies:
        generated = await compose_grounded_results(
            _llm,
            user_input=state["user_input"],
            profile=profile,
            source_type="youthcenter_policy",
            response_mode=response_mode,
            candidates=youth_policies,
        )
        if generated:
            return {"final_response": generated}
        return {"final_response": _compose_youth_policy_response(youth_policies)}

    if not scored:
        if response_mode == "explain":
            text = "공식 데이터에서 요청하신 항목을 찾지 못했어요. 정확한 명칭을 확인해 다시 질문해주세요."
        else:
            text = (
                "입력하신 조건에 맞는 지원사업을 찾지 못했어요. 관심 분야나 지역을 조금 더 알려주시면 다시 찾아볼게요."
            )
        return {"final_response": text}

    generated = await compose_scored_results(
        _llm,
        user_input=state["user_input"],
        response_mode=response_mode,
        profile=profile,
        scored=scored,
    )
    if generated:
        return {"final_response": generated}

    return {"final_response": _compose_with_template(scored)}


# ---------------------------------------------------------------------------
# Conversation Node
# ---------------------------------------------------------------------------


async def conversation_node(state: AgentState) -> dict[str, Any]:
    user_input = state.get("user_input", "")
    response_mode = state.get("response_mode", "general")
    if response_mode == "out_of_scope":
        return {"final_response": OUT_OF_SCOPE_REPLY}
    return {
        "final_response": await compose_conversation_reply(
            _llm,
            query=user_input,
            response_mode=response_mode,
        )
    }


# ---------------------------------------------------------------------------
# Guardrail Node
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS = [
    (re.compile(r"반드시\s*(신청|지원)\s*가능(합니다|해요)?"), "확인해볼 만해요"),
    (re.compile(r"무조건\s*(지원|선정)?\s*(됩니다|돼요|가능합니다)?"), "조건이 맞는지 확인이 필요해요"),
    (re.compile(r"100\s*%\s*(확실|가능)"), "가능성이 높지만 추가 확인이 필요"),
]

_DISCLAIMER = "\n\n※ 최종 자격 및 신청 가능 여부는 공식 공고문 또는 담당 기관을 통해 꼭 확인해주세요."


async def guardrail_node(state: AgentState) -> dict[str, Any]:
    text = state.get("final_response", "")
    notes: list[str] = []

    for pattern, replacement in _FORBIDDEN_PATTERNS:
        if pattern.search(text):
            text = pattern.sub(replacement, text)
            notes.append("확정적 표현을 완화된 표현으로 수정했습니다.")

    has_grounded_results = any(
        state.get(key) for key in ("scored_results", "youth_policy_results", "training_results", "recruitment_results")
    )
    if has_grounded_results and _DISCLAIMER.strip() not in text:
        text = text + _DISCLAIMER

    return {"final_response": text, "guardrail_notes": notes}
