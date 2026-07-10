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

_REGIONS = [
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
]

_VALID_INTENTS = {"RECOMMEND", "EXPLAIN", "ELIGIBILITY_CHECK", "GENERAL", "OUT_OF_SCOPE"}

_ENTREPRENEUR_KEYWORDS = ["창업", "스타트업", "사업을 시작", "사업 시작"]
_JOB_SEEKING_KEYWORDS = ["구직", "취업 준비", "미취업", "취업활동", "일자리"]
_TRAINING_KEYWORDS = ["훈련", "교육", "내일배움", "국비", "강의", "과정", "수강", "배우"]
_RECRUITMENT_KEYWORDS = ["채용", "채용공고", "공고", "인턴", "신입", "공채", "채용행사"]
_EMPLOYED_KEYWORDS = ["재직", "직장인", "다니고 있"]
_STUDENT_KEYWORDS = ["대학생", "재학"]
_OUT_OF_SCOPE_KEYWORDS = ["세무 상담", "법률 자문", "소송", "대출 상담", "회계 처리", "변호사"]
_EXPLAIN_KEYWORDS = [
    "무엇인가요",
    "뭐야",
    "뭐가 좋아",
    "좋은 점",
    "장점",
    "단점",
    "도움",
    "왜",
    "설명해",
    "어떤 내용",
    "무슨 사업",
]
_ELIGIBILITY_KEYWORDS = ["자격 되나요", "신청 가능한가요", "받을 수 있나요", "해당되나요", "자격이 되는지"]
_RECOMMEND_KEYWORDS = [
    "추천",
    "지원사업",
    "지원금",
    "정책",
    "받을 수 있는",
    "찾아줘",
    "있을까",
    "있어",
    *_TRAINING_KEYWORDS,
    *_RECRUITMENT_KEYWORDS,
]

_INTEREST_KEYWORDS = {
    "데이터 분석": ["데이터 분석", "데이터", "분석가", "분석"],
    "AI": ["AI", "인공지능", "머신러닝"],
    "IT": ["IT", "개발", "프로그래밍", "소프트웨어", "앱"],
    "요식업": ["요식업", "카페", "음식점", "식당"],
    "제조업": ["제조업", "제조", "공장"],
    "디자인": ["디자인"],
    "콘텐츠": ["콘텐츠", "영상", "크리에이터"],
    "농업": ["농업", "귀농"],
}


def _classify_request_kind(text: str, profile: dict[str, Any] | None = None) -> str:
    profile = profile or {}
    if any(k in text for k in _TRAINING_KEYWORDS):
        return "training"
    if any(k in text for k in _RECRUITMENT_KEYWORDS):
        return "recruitment"
    if profile.get("is_entrepreneur") or any(k in text for k in _ENTREPRENEUR_KEYWORDS):
        return "business"
    return "youth_policy"


def _extract_training_search_keyword(text: str) -> str | None:
    if "데이터" in text and "분석" in text:
        return "데이터 분석"
    if "빅데이터" in text:
        return "빅데이터"
    if "인공지능" in text:
        return "인공지능"
    if "AI" in text:
        return "AI"
    if "개발" in text:
        return "개발"
    if "프로그래밍" in text:
        return "프로그래밍"
    if "마케팅" in text:
        return "마케팅"
    if "디자인" in text:
        return "디자인"
    return None


# ---------------------------------------------------------------------------
# Router Node
# ---------------------------------------------------------------------------


async def router_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]
    intent = None
    heuristic_intent = _heuristic_route(user_input)

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

    if (
        intent in (None, "GENERAL")
        and heuristic_intent == "RECOMMEND"
        and any(k in user_input for k in _TRAINING_KEYWORDS + _RECRUITMENT_KEYWORDS)
    ):
        intent = "RECOMMEND"

    if intent not in _VALID_INTENTS:
        intent = heuristic_intent

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

    request_kind = _classify_request_kind(user_input, merged)
    merged["request_kind"] = request_kind

    return {"profile": merged, "request_kind": request_kind}


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
        profile["has_registered_business"] = not any(neg in text for neg in ["안 했", "안했", "없", "아직", "미등록"])

    matched_fields = [field for field, kws in _INTEREST_KEYWORDS.items() if any(k in text for k in kws)]
    if matched_fields:
        profile["interest_fields"] = matched_fields
        profile["desired_job"] = matched_fields[0]

    desired_job_match = re.search(r"([가-힣A-Za-z0-9+# ]{2,20})\s*(쪽|분야|직무)로", text)
    if desired_job_match and not profile.get("desired_job"):
        profile["desired_job"] = desired_job_match.group(1).strip()

    if "지원금" in text:
        profile["preferred_support_type"] = "지원금"
    elif any(k in text for k in _TRAINING_KEYWORDS):
        profile["preferred_support_type"] = "훈련"
    elif any(k in text for k in _RECRUITMENT_KEYWORDS):
        profile["preferred_support_type"] = "채용"

    return profile


# ---------------------------------------------------------------------------
# Missing Slot Node
# ---------------------------------------------------------------------------


async def missing_slot_node(state: AgentState) -> dict[str, Any]:
    profile = state.get("profile") or {}
    request_kind = state.get("request_kind") or profile.get("request_kind") or "youth_policy"
    missing: list[str] = []

    if request_kind == "training":
        if not profile.get("desired_job") and not profile.get("interest_fields"):
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

    if request_kind == "training":
        desired_job = (
            profile.get("desired_job")
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
            desired_job=profile.get("desired_job"),
            preferred_work_region=profile.get("region"),
            keywords=state["user_input"],
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
        keywords=state["user_input"],
    )
    youth_input = YouthPolicySearchInput(
        region=profile.get("region"),
        age=profile.get("age"),
        employment_status=profile.get("employment_status"),
        graduation_status=profile.get("graduation_status"),
        support_types=[profile["preferred_support_type"]] if profile.get("preferred_support_type") else [],
        interest_fields=profile.get("interest_fields", []),
        keywords=state["user_input"],
    )
    results = await _search_tool.execute(search_input)
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

    if training_courses:
        return {"final_response": _compose_training_response(training_courses)}

    if recruitment_items:
        return {"final_response": _compose_recruitment_response(recruitment_items)}

    if youth_policies:
        return {"final_response": _compose_youth_policy_response(youth_policies)}

    if not scored:
        text = "입력하신 조건에 맞는 지원사업을 찾지 못했어요. 관심 분야나 지역을 조금 더 알려주시면 다시 찾아볼게요."
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
    lines = [
        "현재 파악한 조건을 바탕으로 확인해볼 만한 지원사업을 정리했어요.",
        "최종 신청 가능 여부는 공고별 세부 조건에 따라 달라질 수 있어요.",
    ]
    for idx, item in enumerate(scored, start=1):
        policy = item["policy"]
        lines.append("")
        lines.append(f"{idx}. {policy['title']} ({policy['agency']})")
        lines.append(f"   - 추천 이유: {' '.join(item['match_reasons']) or '입력 조건과 일부 항목이 맞습니다.'}")
        lines.append(f"   - 지원 대상: {policy['target_description']}")
        lines.append(f"   - 지원 내용: {policy['support_content']}")
        lines.append(
            "   - 신청 기간: "
            f"{policy.get('apply_start') or '상시'} ~ {policy.get('apply_end') or '상시'} "
            f"[{item['deadline_status']}]"
        )
        lines.append(f"   - 신청 방법: {policy['apply_method']}")
        if item["follow_up_checks"]:
            lines.append(f"   - 신청 전 확인 필요: {' '.join(item['follow_up_checks'])}")
        else:
            lines.append("   - 신청 전 확인 필요: 소득, 거주기간, 중복 수혜 제한 등 세부 조건")
        lines.append(f"   - 원문 링크: {policy['source_url']}")
    return "\n".join(lines)


def _compose_youth_policy_response(items: list[dict]) -> str:
    lines = [
        "현재 조건을 기준으로 확인해볼 만한 청년지원사업을 정리했어요.",
        "온통청년 키가 없거나 결과가 부족한 경우에는 내부 정책 데이터로 보완했어요.",
    ]
    for idx, item in enumerate(items[:3], start=1):
        lines.append("")
        lines.append(f"{idx}. {item['title']}")
        if item.get("organization"):
            lines.append(f"   - 운영/주관: {item['organization']}")
        if item.get("region"):
            lines.append(f"   - 지역: {item['region']}")
        lines.append(f"   - 지원 대상: {item.get('target_summary') or '공식 공고 확인 필요'}")
        lines.append(f"   - 지원 내용: {item.get('support_summary') or '공식 공고 확인 필요'}")
        lines.append(f"   - 신청 기간: {item.get('application_period') or '공식 공고 확인 필요'}")
        lines.append(f"   - 신청 방법: {item.get('application_method') or '공식 공고 확인 필요'}")
        lines.append(f"   - 원문 링크: {item.get('detail_url') or '공식 사이트 확인 필요'}")
        if item.get("fallback_reason"):
            lines.append(f"   - 데이터 안내: {item['fallback_reason']}")
    lines.append("")
    lines.append("최종 자격과 신청 가능 여부는 공고 원문 또는 담당 기관에서 꼭 확인해주세요.")
    return "\n".join(lines)


def _compose_training_response(items: list[dict]) -> str:
    guide_items = [item for item in items if item.get("course_id") == "work24-training-guide"]
    if guide_items:
        guide = guide_items[0]
        return (
            "고용24 훈련과정 API에서 조건에 맞는 과정을 바로 찾지 못했어요.\n"
            "대신 아래 링크와 검색어로 고용24에서 직접 확인해보세요.\n\n"
            f"- 검색 링크: {guide.get('detail_url') or 'https://www.work24.go.kr/cm/main.do'}\n"
            f"- 추천 검색어: {guide.get('raw', {}).get('search_keyword') or guide.get('title')}\n"
            f"- 지역 조건: {guide.get('region') or '전체 또는 희망 지역'}\n"
            "- 확인 위치: 고용24 > 직업 능력 개발 > 훈련 찾기·신청\n"
            f"- 데이터 안내: {guide.get('fallback_reason') or '검색 결과 없음'}"
        )

    lines = [
        "고용24 국민내일배움카드 훈련과정에서 확인해볼 만한 과정을 정리했어요.",
        "수강 가능 여부와 자비부담액은 고용24 상세 화면에서 다시 확인해주세요.",
    ]
    for idx, item in enumerate(items[:3], start=1):
        lines.append("")
        lines.append(f"{idx}. {item['title']}")
        lines.append(f"   - 훈련기관: {item.get('institution') or '기관명 확인 필요'}")
        lines.append(f"   - 지역/주소: {item.get('region') or item.get('address') or '지역 확인 필요'}")
        lines.append(
            "   - 훈련 기간: "
            f"{item.get('start_date') or '시작일 확인 필요'} ~ {item.get('end_date') or '종료일 확인 필요'}"
        )
        lines.append(f"   - 비용: {item.get('cost') or item.get('actual_cost') or '고용24 상세 확인 필요'}")
        if item.get("ncs_code"):
            lines.append(f"   - NCS 코드: {item['ncs_code']}")
        lines.append(f"   - 상세 URL: {item.get('detail_url') or '고용24에서 과정명으로 검색 필요'}")
        if item.get("fallback_reason"):
            lines.append(f"   - 데이터 안내: {item['fallback_reason']}")
    return "\n".join(lines)


def _compose_recruitment_response(items: list[dict]) -> str:
    guide_items = [item for item in items if item.get("item_type") == "guide"]
    if guide_items:
        guide = guide_items[0]
        return (
            f"{guide['title']}\n"
            f"- 안내: {guide.get('summary') or '고용24에서 관심 직무와 지역 기준으로 다시 검색해주세요.'}\n"
            f"- 확인 링크: {guide.get('detail_url') or 'https://www.work24.go.kr/'}\n"
            f"- 제한 사유: {guide.get('fallback_reason') or '개인회원 API 권한 제한 또는 결과 없음'}\n\n"
            "제가 없는 채용공고를 만들어 안내하지는 않을게요. 관심 직무와 희망 지역을 알려주시면 "
            "검색 키워드와 확인해야 할 공고 조건을 더 구체적으로 정리해드릴 수 있어요."
        )

    lines = ["고용24에서 확인된 채용 관련 보조 정보를 정리했어요."]
    for idx, item in enumerate(items[:3], start=1):
        lines.append("")
        lines.append(f"{idx}. {item['title']}")
        if item.get("company"):
            lines.append(f"   - 기업: {item['company']}")
        if item.get("region"):
            lines.append(f"   - 지역: {item['region']}")
        if item.get("end_date"):
            lines.append(f"   - 마감일: {item['end_date']}")
        if item.get("summary"):
            lines.append(f"   - 요약: {item['summary']}")
        lines.append(f"   - 원문 링크: {item.get('detail_url') or '고용24 상세 확인 필요'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Explain / General / Out-of-scope Nodes
# ---------------------------------------------------------------------------


async def explain_node(state: AgentState) -> dict[str, Any]:
    query = state["user_input"]
    policy = await _policy_repo.find_best_title_match(query)
    if not policy:
        return {"final_response": await _compose_general_explanation(query)}
    text = (
        f"'{policy['title']}'({policy['agency']}) 안내드릴게요.\n"
        f"- 지원 대상: {policy['target_description']}\n"
        f"- 지원 내용: {policy['support_content']}\n"
        f"- 신청 기간: {policy.get('apply_start') or '상시'} ~ {policy.get('apply_end') or '상시'}\n"
        f"- 신청 방법: {policy['apply_method']}\n"
        f"- 원문 링크: {policy['source_url']}"
    )
    return {"final_response": text}


async def _compose_general_explanation(query: str) -> str:
    if _llm.is_configured:
        try:
            return await _llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "당신은 청년 정책과 취업지원 제도를 설명하는 상담형 AI입니다. "
                            "사용자가 특정 과정 검색이나 정책 추천을 요청하지 않고 제도, 장점, "
                            "주의점, 선택 기준을 물으면 일반 설명으로 답하세요. "
                            "실시간 공고명, 금액, 자격, URL은 새로 만들어내지 말고, "
                            "필요하면 고용24(https://www.work24.go.kr/) 또는 공식 공고에서 "
                            "확인하라고 안내하세요. work.go.kr 같은 예전 도메인은 쓰지 마세요. "
                            "이모지 없이 답하세요. "
                            "답변은 한국어로, 핵심 bullet 중심으로 간결하게 작성하세요."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                temperature=0.3,
            )
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 일반 설명 템플릿을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("일반 설명 LLM 호출 실패, 템플릿으로 폴백합니다.")

    if any(keyword in query for keyword in ("국비", "내일배움", "훈련", "교육")):
        return (
            "국비지원 훈련은 취업이나 직무 전환을 준비할 때 교육비 부담을 줄이고, "
            "필요한 직무 역량을 체계적으로 배울 수 있다는 점이 좋아요.\n\n"
            "- 장점: 자비부담을 낮출 수 있고, 데이터 분석/개발/사무 등 직무별 과정을 비교할 수 있어요.\n"
            "- 활용 포인트: 과정명보다 커리큘럼, 훈련기관, 수료 후 포트폴리오/취업지원 여부를 같이 보세요.\n"
            "- 주의점: 수강 가능 여부, 자비부담액, 출석 기준, 훈련장려금 여부는 과정마다 달라요.\n"
            "- 확인처: 고용24 국민내일배움카드 훈련과정 상세 화면에서 최신 조건을 확인해야 해요."
        )
    return GENERAL_REPLY


async def general_node(state: AgentState) -> dict[str, Any]:
    user_input = state.get("user_input", "")
    if any(keyword in user_input for keyword in _EXPLAIN_KEYWORDS + _TRAINING_KEYWORDS):
        return {"final_response": await _compose_general_explanation(user_input)}
    return {"final_response": GENERAL_REPLY}


async def out_of_scope_node(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
    return {"final_response": OUT_OF_SCOPE_REPLY}


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
