from __future__ import annotations

import json
import logging
from typing import Any

from app.core.llm import LLMUnavailableError, SolarLLMClient
from app.core.prompts import (
    CONVERSATION_SYSTEM_PROMPT,
    GROUNDED_DATA_RESPONSE_SYSTEM_PROMPT,
    RESPONSE_SYSTEM_PROMPT,
)
from app.graph.fallbacks import general_reply as fallback_general_reply

logger = logging.getLogger(__name__)


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
        "candidates": candidates[:3],
    }
    try:
        return await llm.complete(
            [
                {"role": "system", "content": GROUNDED_DATA_RESPONSE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
    except LLMUnavailableError:
        logger.info("LLM 미설정으로 %s 응답 템플릿을 사용합니다.", source_type)
    except Exception:  # noqa: BLE001
        logger.exception("%s 검색 결과 LLM 생성 실패, 템플릿으로 폴백합니다.", source_type)
    return None


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
        return await llm.complete(
            [
                {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.4,
        )
    except LLMUnavailableError:
        logger.info("LLM 미설정으로 응답 생성 템플릿을 사용합니다.")
    except Exception:  # noqa: BLE001
        logger.exception("응답 생성 LLM 호출 실패, 템플릿으로 폴백합니다.")
    return None


async def compose_conversation_reply(llm: SolarLLMClient, *, query: str, response_mode: str) -> str:
    if llm.is_configured:
        try:
            payload = {"user_input": query, "response_mode": response_mode}
            return await llm.complete(
                [
                    {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.3,
            )
        except LLMUnavailableError:
            logger.info("LLM 미설정으로 일반 대화 템플릿을 사용합니다.")
        except Exception:  # noqa: BLE001
            logger.exception("일반 대화 LLM 호출 실패, 템플릿으로 폴백합니다.")
    return fallback_general_reply(query)


def compose_scored_template(scored: list[dict]) -> str:
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


def compose_youth_policy_response(items: list[dict]) -> str:
    lines = [
        "현재 조건을 기준으로 확인해볼 만한 청년지원사업을 정리했어요.",
        "온통청년 공식 API 조회 결과입니다.",
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
