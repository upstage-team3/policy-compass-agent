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
from app.core.prompts import OUT_OF_SCOPE_REPLY, PROFILE_EXTRACTION_SYSTEM_PROMPT, ROUTER_SYSTEM_PROMPT
from app.core.regions import resolve_region, user_region_reference
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
    clean_response_text,
    compose_clarification_reply,
    compose_conversation_reply,
    compose_grounded_results,
    compose_no_results_reply,
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
from app.repositories.supabase_fallback import (
    SupabaseRecruitmentInfoFallback,
    SupabaseTrainingCourseFallback,
    SupabaseYouthPolicyFallback,
)
from app.repositories.work24_recruitment import Work24RecruitmentRepository
from app.repositories.work24_training import Work24TrainingRepository
from app.repositories.youthcenter import YouthCenterRepository, is_generic_youth_policy_query
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
_youth_policy_tool = YouthPolicySearchTool(YouthCenterRepository(SupabaseYouthPolicyFallback()))
_training_tool = TrainingCourseSearchTool(Work24TrainingRepository(SupabaseTrainingCourseFallback()))
_recruitment_tool = RecruitmentInfoTool(Work24RecruitmentRepository(SupabaseRecruitmentInfoFallback()))

# ---------------------------------------------------------------------------
# Router Node
# ---------------------------------------------------------------------------


async def router_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]
    pending = state.get("pending_request") or {}
    action = None
    response_mode = None
    intent = None
    request_kind = None
    search_query = None
    routing_source = "heuristic"
    resumed_pending = False

    if _llm.is_configured:
        try:
            routing_context = {
                "message": user_input,
                "known_profile": state.get("profile") or {},
                "recent_history": (state.get("conversation_history") or [])[-6:],
                "pending_request": pending,
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
            resumed_pending = decision.resume_pending and bool(pending)
            if resumed_pending:
                action = "SEARCH"
                response_mode = pending.get("response_mode", response_mode)
                request_kind = pending.get("request_kind", request_kind)
                search_query = search_query or pending.get("search_query")
            if request_kind == "youth_policy" and is_generic_youth_policy_query(user_input):
                search_query = None
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
        should_resume_general_answer = action == "RESPOND" and response_mode == "general"
        if pending and (should_resume_general_answer or request_kind == pending.get("request_kind")):
            action = "SEARCH"
            response_mode = pending.get("response_mode", response_mode)
            intent = {
                "recommend": "RECOMMEND",
                "eligibility": "ELIGIBILITY_CHECK",
                "explain": "EXPLAIN",
            }.get(response_mode, intent)
            request_kind = pending.get("request_kind", request_kind)
            search_query = search_query or pending.get("search_query")
            resumed_pending = True
        elif (
            should_resume_general_answer
            and re.search(r"말고|아니라|아니고|대신", user_input)
            and user_region_reference(user_input)
            and state.get("request_kind") in VALID_REQUEST_KINDS - {"general"}
        ):
            # LLM 장애 중에도 완료된 검색의 지역만 정정한 후속 발화는
            # 직전 Tool과 검색어를 유지해 새 지역으로 다시 조회한다.
            action = "SEARCH"
            response_mode = state.get("response_mode", "recommend")
            intent = {
                "recommend": "RECOMMEND",
                "eligibility": "ELIGIBILITY_CHECK",
                "explain": "EXPLAIN",
            }.get(response_mode, "RECOMMEND")
            request_kind = state["request_kind"]
            search_query = state.get("search_query")

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
        "resumed_pending": resumed_pending,
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
            extraction_context = {
                "message": user_input,
                "known_profile": previous_profile,
                "recent_history": (state.get("conversation_history") or [])[-6:],
                "pending_request": state.get("pending_request") or {},
            }
            raw = await _llm.complete(
                [
                    {"role": "system", "content": PROFILE_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(extraction_context, ensure_ascii=False)},
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

    # 지역은 LLM이 known_profile이나 상식으로 시·도를 보완하지 못하게 현재 발화의
    # 공식 행정구역 표현만 다시 읽어 덮어쓴다. 모호한 고성군·중구는 그대로 남겨
    # Missing Slot 단계가 시·도 확인 질문을 하도록 한다.
    explicit_region = user_region_reference(user_input)
    if explicit_region:
        extracted["region"] = explicit_region
    else:
        extracted.pop("region", None)

    broad_policy_request = is_generic_youth_policy_query(user_input)
    if broad_policy_request:
        extracted.pop("policy_topic", None)

    merged = {**previous_profile}
    if broad_policy_request:
        merged.pop("policy_topic", None)
    for key, value in extracted.items():
        if value in (None, "", []):
            continue
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

    topic_listing_explanation = request_kind == "youth_policy" and bool(profile.get("policy_topic"))
    if state.get("response_mode") == "explain" and not topic_listing_explanation:
        return {"missing_slots": []}

    region = profile.get("region")
    unresolved_region = bool(region and resolve_region(region) is None)

    if request_kind == "training":
        if not state.get("search_query") and not profile.get("desired_job") and not profile.get("interest_fields"):
            missing.append("desired_job")
        if not region:
            missing.append("training_region")
        elif unresolved_region:
            missing.append("region_detail")
    elif request_kind == "recruitment":
        if not state.get("search_query") and not profile.get("desired_job") and not profile.get("interest_fields"):
            missing.append("desired_job")
        if not region:
            missing.append("work_region")
        elif unresolved_region:
            missing.append("region_detail")
    elif request_kind == "business":
        if not region:
            missing.append("region")
        elif unresolved_region:
            missing.append("region_detail")
        if profile.get("is_entrepreneur") is None:
            missing.append("business_status")
        elif profile.get("is_entrepreneur") and profile.get("has_registered_business") is None:
            missing.append("business_registration")
    else:
        if not region:
            missing.append("region")
        elif unresolved_region:
            missing.append("region_detail")
        if profile.get("age") is None:
            missing.append("age")
        policy_topic = profile.get("policy_topic")
        has_specific_query = bool(
            state.get("search_query") and not is_generic_youth_policy_query(state.get("search_query"))
        )
        if (
            not policy_topic
            and not has_specific_query
            and not profile.get("preferred_support_type")
            and not profile.get("interest_fields")
        ):
            missing.append("policy_topic")
        if policy_topic == "일자리" and profile.get("employment_status") is None:
            missing.append("employment_status")

    return {"missing_slots": missing}


async def clarification_node(state: AgentState) -> dict[str, Any]:
    missing = state.get("missing_slots", [])
    existing = state.get("pending_request") or {}
    if state.get("resumed_pending") and existing:
        pending = dict(existing)
    else:
        pending = {
            "original_request": state.get("user_input", ""),
            "request_kind": state.get("request_kind", "youth_policy"),
            "response_mode": state.get("response_mode", "recommend"),
            "search_query": state.get("search_query"),
        }
    next_query = state.get("search_query")
    policy_topic = (state.get("profile") or {}).get("policy_topic")
    if policy_topic and is_generic_youth_policy_query(next_query):
        next_query = policy_topic
    if next_query:
        pending["search_query"] = next_query
    question = await compose_clarification_reply(
        _llm,
        original_request=pending.get("original_request") or state.get("user_input", ""),
        profile=state.get("profile") or {},
        missing_slots=missing,
        history=state.get("conversation_history") or [],
    )
    return {
        "final_response": question,
        "pending_request": pending,
        "search_results": [],
        "youth_policy_results": [],
        "training_results": [],
        "recruitment_results": [],
        "scored_results": [],
    }


# ---------------------------------------------------------------------------
# Policy Search + Eligibility Scorer Nodes
# ---------------------------------------------------------------------------


async def policy_search_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    request_kind = state.get("request_kind") or profile.get("request_kind") or "youth_policy"
    pending = state.get("pending_request") or {}
    state_query = state.get("search_query")
    pending_query = pending.get("search_query")
    if request_kind == "youth_policy":
        if state_query and not is_generic_youth_policy_query(state_query):
            planned_query = state_query
        elif profile.get("policy_topic"):
            planned_query = profile["policy_topic"]
        elif pending_query and not is_generic_youth_policy_query(pending_query):
            planned_query = pending_query
        else:
            planned_query = state_query or pending_query
    else:
        planned_query = state_query or pending_query
    original_request = pending.get("original_request") or state["user_input"]
    search_context = {
        "original_request": original_request,
        "search_query": planned_query,
        "request_kind": request_kind,
    }

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
            keywords=original_request,
        )
        results = await _training_tool.execute(training_input)
        return {
            "search_results": [],
            "youth_policy_results": [],
            "training_results": [item.model_dump() for item in results],
            "recruitment_results": [],
            "pending_request": {},
            "search_context": search_context,
        }

    if request_kind == "recruitment":
        recruitment_input = RecruitmentInfoSearchInput(
            desired_job=planned_query or profile.get("desired_job"),
            preferred_work_region=profile.get("region"),
            keywords=planned_query or original_request,
        )
        results = await _recruitment_tool.execute(recruitment_input)
        return {
            "search_results": [],
            "youth_policy_results": [],
            "training_results": [],
            "recruitment_results": [item.model_dump() for item in results],
            "pending_request": {},
            "search_context": search_context,
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
        keywords=planned_query or original_request,
    )
    youth_input = YouthPolicySearchInput(
        region=profile.get("region"),
        age=profile.get("age"),
        employment_status=profile.get("employment_status"),
        graduation_status=profile.get("graduation_status"),
        support_types=[
            value for value in (profile.get("policy_topic"), profile.get("preferred_support_type")) if value
        ],
        interest_fields=profile.get("interest_fields", []),
        keywords=planned_query or original_request,
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
        "pending_request": {},
        "search_context": search_context,
    }


async def eligibility_scorer_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    scored = [score_policy(profile, policy) for policy in state.get("search_results", [])]
    recommended = [item for item in scored if item["is_recommendable"]]
    recommended.sort(
        key=lambda item: (item["match_score"], item["evidence_coverage"]),
        reverse=True,
    )
    if recommended:
        return {"scored_results": recommended[:5]}

    nearby = [
        item
        for item in scored
        if item["recommendation_scope"] == "nearby_reference" and item["deadline_status"] != "마감"
    ]
    nearby.sort(key=lambda item: item["policy"].get("distance_km") or float("inf"))
    return {"scored_results": nearby[:3]}


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
    search_context = state.get("search_context") or {}
    original_request = search_context.get("original_request") or state["user_input"]

    if training_courses:
        generated = await compose_grounded_results(
            _llm,
            user_input=original_request,
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
            user_input=original_request,
            profile=profile,
            source_type="work24_recruitment",
            response_mode=response_mode,
            candidates=recruitment_items,
        )
        if generated:
            return {"final_response": generated}
        return {"final_response": _compose_recruitment_response(recruitment_items)}

    if youth_policies:
        if any(item.get("policy_id") == "youthcenter-guide" for item in youth_policies):
            return {"final_response": _compose_youth_policy_response(youth_policies)}
        generated = await compose_grounded_results(
            _llm,
            user_input=original_request,
            profile=profile,
            source_type="youthcenter_policy",
            response_mode=response_mode,
            candidates=youth_policies,
        )
        if generated:
            return {"final_response": generated}
        return {"final_response": _compose_youth_policy_response(youth_policies)}

    if not scored:
        source_type = {
            "youth_policy": "youthcenter_policy",
            "training": "work24_training",
            "recruitment": "work24_recruitment",
            "business": "bizinfo",
        }.get(state.get("request_kind"), "policy")
        text = await compose_no_results_reply(
            _llm,
            user_input=original_request,
            profile=profile,
            source_type=source_type,
            search_query=search_context.get("search_query"),
        )
        return {"final_response": text}

    generated = await compose_scored_results(
        _llm,
        user_input=original_request,
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
            history=state.get("conversation_history") or [],
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

_DISCLAIMER = "\n\n최종 신청 가능 여부는 공식 공고나 담당 기관에서 한 번 더 확인해 주세요."
_GENERATED_DISCLAIMER = re.compile(
    r"(?m)^\s*(?:[-•]\s*)?(?:※\s*)?(?:모든\s*정책\s*)?(?:최종\s*)?자격.*"
    r"(?:공식\s*공고|담당\s*기관).*$"
)


async def guardrail_node(state: AgentState) -> dict[str, Any]:
    text = clean_response_text(state.get("final_response", ""))
    notes: list[str] = []

    for pattern, replacement in _FORBIDDEN_PATTERNS:
        if pattern.search(text):
            text = pattern.sub(replacement, text)
            notes.append("확정적 표현을 완화된 표현으로 수정했습니다.")

    has_grounded_results = any(
        state.get(key) for key in ("scored_results", "youth_policy_results", "training_results", "recruitment_results")
    )
    if has_grounded_results:
        text = clean_response_text(_GENERATED_DISCLAIMER.sub("", text))
        text = text.rstrip() + _DISCLAIMER

    history = list(state.get("conversation_history") or [])
    history.extend(
        [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": text},
        ]
    )
    return {
        "final_response": text,
        "guardrail_notes": notes,
        "conversation_history": history[-8:],
    }
