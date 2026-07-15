from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.llm import LLMUnavailableError, SolarLLMClient
from app.core.prompts import (
    CLARIFICATION_SYSTEM_PROMPT,
    CONVERSATION_SYSTEM_PROMPT,
    GROUNDED_DATA_RESPONSE_SYSTEM_PROMPT,
    MISSING_SLOT_LABELS,
    NO_RESULTS_SYSTEM_PROMPT,
    RESPONSE_SYSTEM_PROMPT,
)
from app.graph.fallbacks import general_reply as fallback_general_reply

logger = logging.getLogger(__name__)

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)]\((https?://[^)]+)\)")
_FORMAL_INTRO = re.compile(
    r"사용자님의\s*질문\s*\([^\n]*\)\s*에\s*따라,[^\n]*(?:추천|안내)합니다\.?\s*",
)
_INTERNAL_FIELD_LABELS = {
    "application_period": "신청 기간",
    "application_method": "신청 방법",
    "detail_url": "상세 링크",
    "business_period": "사업 기간",
}


def clean_response_text(text: str) -> str:
    """Keep chat responses readable in a plain-text UI even if an LLM emits Markdown."""

    cleaned = _FORMAL_INTRO.sub("", text or "")
    cleaned = _MARKDOWN_LINK.sub(r"\1 (\2)", cleaned)
    for internal_name, label in _INTERNAL_FIELD_LABELS.items():
        cleaned = cleaned.replace(internal_name, label)

    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", raw_line)
        line = re.sub(r"^\s*>\s?", "", line)
        line = re.sub(r"^\s*\*\s+", "- ", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if line.strip().rstrip(":") in {"답변", "추천 정책", "안내 사항"}:
            continue
        if "누락된 신청 정보" in line:
            continue
        lines.append(line.rstrip())

    result = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


def _compact_candidates(candidates: list[dict]) -> list[dict]:
    compact: list[dict] = []
    for candidate in candidates[:3]:
        item = {}
        for key, value in candidate.items():
            if key == "raw":
                continue
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str):
                item[key] = value[:1200]
            elif isinstance(value, dict):
                item[key] = {
                    nested_key: nested_value for nested_key, nested_value in value.items() if nested_key != "raw"
                }
            else:
                item[key] = value
        if candidate.get("source") == "youthcenter":
            missing = [
                label
                for key, label in (
                    ("application_period", "신청 기간"),
                    ("application_method", "신청 방법"),
                    ("detail_url", "상세 링크"),
                )
                if not candidate.get(key)
            ]
            if missing:
                item["data_notice"] = f"온통청년 API에 {'·'.join(missing)} 정보가 등록되어 있지 않아요."
        compact.append(item)
    return compact


async def compose_clarification_reply(
    llm: SolarLLMClient,
    *,
    original_request: str,
    profile: dict[str, Any],
    missing_slots: list[str],
    history: list[dict[str, str]],
) -> str:
    labels = [MISSING_SLOT_LABELS.get(slot, slot) for slot in missing_slots]
    if llm.is_configured:
        payload = {
            "original_request": original_request,
            "known_profile": profile,
            "missing_slots": labels,
            "recent_history": history[-6:],
        }
        try:
            return clean_response_text(
                await llm.complete(
                    [
                        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    temperature=0.2,
                )
            )
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 조건 확인 템플릿을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("조건 확인 LLM 호출 실패, 템플릿으로 폴백합니다.")
    return clarification_template(labels)


def clarification_template(labels: list[str]) -> str:
    return "정확한 결과를 찾으려면 다음 정보가 필요해요: " + ", ".join(labels) + "."


async def compose_grounded_results(
    llm: SolarLLMClient,
    *,
    user_input: str,
    profile: dict[str, Any],
    source_type: str,
    response_mode: str,
    candidates: list[dict],
) -> str | None:
    if not llm.is_configured:
        return None

    payload = {
        "user_input": user_input,
        "profile": profile,
        "source_type": source_type,
        "response_mode": response_mode,
        "candidates": _compact_candidates(candidates),
    }
    try:
        return clean_response_text(
            await llm.complete(
                [
                    {"role": "system", "content": GROUNDED_DATA_RESPONSE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.2,
            )
        )
    except LLMUnavailableError:
        logger.info("LLM 미설정으로 %s 응답 템플릿을 사용합니다.", source_type)
    except Exception:  # noqa: BLE001
        logger.exception("%s 검색 결과 LLM 생성 실패, 템플릿으로 폴백합니다.", source_type)
    return None


async def compose_no_results_reply(
    llm: SolarLLMClient,
    *,
    user_input: str,
    profile: dict[str, Any],
    source_type: str,
    search_query: str | None,
) -> str:
    if source_type == "youthcenter_policy":
        region = profile.get("region")
        conditions = [f"{region} 지역" if region else None, f"'{search_query}' 검색어" if search_query else None]
        condition_text = "의 ".join(value for value in conditions if value)
        condition_prefix = f"{condition_text}에 맞는 " if condition_text else ""
        return (
            f"온통청년 청년정책에서 {condition_prefix}검색 결과를 찾지 못했어요. "
            "현재 조회 결과 기준으로 안내할 정책이 없습니다."
        )

    payload = {
        "original_request": user_input,
        "known_profile": profile,
        "source_type": source_type,
        "search_query": search_query,
    }
    if llm.is_configured:
        try:
            return clean_response_text(
                await llm.complete(
                    [
                        {"role": "system", "content": NO_RESULTS_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    temperature=0.2,
                )
            )
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 검색 결과 없음 템플릿을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("검색 결과 없음 LLM 호출 실패, 템플릿으로 폴백합니다.")

    source_names = {
        "youthcenter_policy": "온통청년 청년정책",
        "work24_training": "고용24 훈련과정",
        "work24_recruitment": "고용24 채용 보조정보",
        "bizinfo": "기업마당 지원사업",
    }
    source_name = source_names.get(source_type, "공식 정책 데이터")
    query_hint = f" '{search_query}' 검색어" if search_query else " 현재 조건"
    return (
        f"{source_name}에서{query_hint}에 맞는 결과를 찾지 못했어요. "
        "이미 알려주신 조건은 유지할게요. 관심 분야를 조금 넓히거나 다른 표현으로 말씀해주시면 다시 찾아볼게요."
    )


async def compose_scored_results(
    llm: SolarLLMClient,
    *,
    user_input: str,
    response_mode: str,
    profile: dict,
    scored: list[dict],
) -> str | None:
    if not llm.is_configured:
        return None
    payload = {
        "user_input": user_input,
        "response_mode": response_mode,
        "profile": profile,
        "candidates": scored,
    }
    try:
        return clean_response_text(
            await llm.complete(
                [
                    {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.4,
            )
        )
    except LLMUnavailableError:
        logger.info("LLM 미설정으로 응답 생성 템플릿을 사용합니다.")
    except Exception:  # noqa: BLE001
        logger.exception("응답 생성 LLM 호출 실패, 템플릿으로 폴백합니다.")
    return None


async def compose_conversation_reply(
    llm: SolarLLMClient,
    *,
    query: str,
    response_mode: str,
    history: list[dict[str, str]],
) -> str:
    if llm.is_configured:
        try:
            payload = {
                "user_input": query,
                "response_mode": response_mode,
                "recent_history": history[-8:],
            }
            return clean_response_text(
                await llm.complete(
                    [
                        {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    temperature=0.3,
                )
            )
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 일반 대화 템플릿을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("일반 대화 LLM 호출 실패, 템플릿으로 폴백합니다.")
    return fallback_general_reply(query)


def compose_scored_template(scored: list[dict]) -> str:
    """세부 내용은 프론트 카드로 표시되므로, 여기서는 짧은 안내 멘트만 반환한다."""

    nearby_only = bool(scored) and all(item.get("recommendation_scope") == "nearby_reference" for item in scored)
    if nearby_only:
        return (
            "요청 지역에 정확히 일치하거나 전국 대상인 지원사업은 찾지 못했어요. "
            "아래 카드는 가까운 지역 참고 결과이며, 거주 요건 때문에 신청하지 못할 수 있어요."
        )
    return (
        f"현재 조건에 맞는 지원사업 {len(scored)}건을 아래 카드로 정리했어요. "
        "최종 신청 가능 여부는 카드의 원문 링크에서 확인해주세요."
    )


def compose_youth_policy_response(items: list[dict]) -> str:
    guide_items = [item for item in items if item.get("policy_id") == "youthcenter-guide"]
    if guide_items:
        return (
            "온통청년 공식 API에서 정책 데이터를 확인하지 못했어요.\n"
            "정책이 없다고 판단한 것은 아니며, 연결 상태를 확인한 뒤 다시 검색해야 해요.\n\n"
            f"데이터 안내: {guide_items[0].get('fallback_reason') or '일시적인 API 응답 실패'}"
        )

    nearby_only = bool(items) and all(item.get("match_scope") == "nearby" for item in items)
    if nearby_only:
        return (
            "요청 지역에 정확히 일치하거나 전국 대상인 청년정책은 찾지 못했어요. "
            "아래 카드는 가까운 지역 참고 결과이며, 해당 지역 거주 요건 때문에 신청하지 못할 수 있어요."
        )
    shown = items[:3]
    return (
        f"현재 조건에 맞는 청년지원사업 {len(shown)}건을 아래 카드로 정리했어요. "
        "최종 자격과 신청 가능 여부는 카드의 상세 링크에서 확인해주세요."
    )


def compose_training_response(items: list[dict]) -> str:
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

    shown = items[:3]
    return (
        f"고용24 국민내일배움카드 훈련과정 {len(shown)}건을 아래 카드로 정리했어요. "
        "수강 가능 여부와 자비부담액은 카드의 상세 링크에서 다시 확인해주세요."
    )


def compose_recruitment_response(items: list[dict]) -> str:
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

    shown = items[:3]
    return f"고용24에서 확인된 채용 관련 보조 정보 {len(shown)}건을 아래 카드로 정리했어요."
