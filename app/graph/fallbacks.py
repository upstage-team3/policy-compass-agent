from __future__ import annotations

import re
from typing import Any

from app.core.prompts import GENERAL_REPLY
from app.core.regions import user_region_reference

ENTREPRENEUR_KEYWORDS = ["창업", "스타트업", "사업을 시작", "사업 시작"]
JOB_SEEKING_KEYWORDS = ["구직", "취업 준비", "미취업", "취업활동", "일자리"]
TRAINING_KEYWORDS = ["훈련", "교육", "내일배움", "국비", "강의", "과정", "수강", "배우"]
RECRUITMENT_KEYWORDS = ["채용", "채용공고", "공고", "인턴", "신입", "공채", "채용행사"]
EMPLOYED_KEYWORDS = ["재직", "직장인", "다니고 있"]
STUDENT_KEYWORDS = ["대학생", "재학"]
OUT_OF_SCOPE_KEYWORDS = ["세무 상담", "법률 자문", "소송", "대출 상담", "회계 처리", "변호사"]
EXPLAIN_KEYWORDS = [
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
ELIGIBILITY_KEYWORDS = ["자격 되나요", "신청 가능한가요", "받을 수 있나요", "해당되나요", "자격이 되는지"]
RECOMMEND_KEYWORDS = [
    "추천",
    "지원사업",
    "지원금",
    "정책",
    "받을 수 있는",
    "찾아줘",
    "있을까",
    "있어",
    "금융지원",
    *TRAINING_KEYWORDS,
    *RECRUITMENT_KEYWORDS,
]

YOUTH_POLICY_SPECIFIC_QUERY_KEYWORDS = (
    "월세",
    "전세",
    "주거비",
    "금융",
    "자산형성",
    "문화",
    "건강",
)

INTEREST_KEYWORDS = {
    "데이터 분석": ["데이터 분석", "데이터", "분석가", "분석"],
    "클라우드 엔지니어": ["클라우드", "AWS", "Azure", "DevOps"],
    "AI": ["AI", "인공지능", "머신러닝"],
    "IT": ["IT", "개발", "프로그래밍", "소프트웨어", "앱"],
    "요식업": ["요식업", "카페", "음식점", "식당"],
    "제조업": ["제조업", "제조", "공장"],
    "디자인": ["디자인"],
    "콘텐츠": ["콘텐츠", "영상", "크리에이터"],
    "농업": ["농업", "귀농"],
}

POLICY_TOPIC_KEYWORDS = {
    "일자리": ["취업", "구직", "일자리", "일경험"],
    "주거": ["주거", "거주지원", "월세", "전세", "임대", "주거비"],
    "교육·직업·훈련": ["교육", "직업훈련", "역량", "자격증"],
    "금융·복지·문화": ["금융", "자산", "복지", "생활", "문화", "건강"],
    "참여·기반": ["참여", "권리", "청년활동", "커뮤니티"],
}


def classify_request_kind(text: str, profile: dict[str, Any] | None = None) -> str:
    profile = profile or {}
    policy_request = any(keyword in text for keyword in ("정책", "지원사업", "청년지원"))
    course_request = any(keyword in text for keyword in ("훈련", "내일배움", "국비", "과정", "수강", "강의"))
    if any(keyword in text for keyword in TRAINING_KEYWORDS) and (course_request or not policy_request):
        return "training"
    if any(keyword in text for keyword in RECRUITMENT_KEYWORDS):
        return "recruitment"
    if profile.get("is_entrepreneur") or any(keyword in text for keyword in ENTREPRENEUR_KEYWORDS):
        return "business"
    return "youth_policy"


def extract_training_search_keyword(text: str) -> str | None:
    rules = [
        (("데이터", "분석"), "데이터 분석"),
        (("빅데이터",), "빅데이터"),
        (("인공지능",), "인공지능"),
        (("AI",), "AI"),
        (("클라우드",), "클라우드 엔지니어"),
        (("개발",), "개발"),
        (("프로그래밍",), "프로그래밍"),
        (("마케팅",), "마케팅"),
        (("디자인",), "디자인"),
    ]
    for keywords, result in rules:
        if all(keyword in text for keyword in keywords):
            return result
    return None


def extract_youth_policy_search_keyword(text: str) -> str | None:
    """LLM 장애 시에도 구체적인 청년정책 하위 유형을 넓히지 않는다."""

    compact = re.sub(r"\s+", "", text)
    return next((keyword for keyword in YOUTH_POLICY_SPECIFIC_QUERY_KEYWORDS if keyword in compact), None)


def heuristic_route(text: str) -> str:
    if any(keyword in text for keyword in OUT_OF_SCOPE_KEYWORDS):
        return "OUT_OF_SCOPE"
    if any(keyword in text for keyword in ELIGIBILITY_KEYWORDS):
        return "ELIGIBILITY_CHECK"
    if any(keyword in text for keyword in EXPLAIN_KEYWORDS):
        return "EXPLAIN"
    if any(keyword in text for keyword in RECOMMEND_KEYWORDS) or any(
        keyword in text for keyword in JOB_SEEKING_KEYWORDS + ENTREPRENEUR_KEYWORDS
    ):
        return "RECOMMEND"
    return "GENERAL"


def routing_plan(text: str, profile: dict[str, Any] | None = None) -> dict[str, str | None]:
    intent = heuristic_route(text)
    if intent == "RECOMMEND":
        request_kind = classify_request_kind(text, profile)
        return {
            "intent": intent,
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": request_kind,
            "search_query": extract_youth_policy_search_keyword(text) if request_kind == "youth_policy" else None,
        }
    if intent == "ELIGIBILITY_CHECK":
        return {
            "intent": intent,
            "action": "SEARCH",
            "response_mode": "eligibility",
            "request_kind": classify_request_kind(text, profile),
            "search_query": None,
        }
    if intent == "EXPLAIN":
        return {
            "intent": intent,
            "action": "RESPOND",
            "response_mode": "explain",
            "request_kind": "general",
            "search_query": None,
        }
    if intent == "OUT_OF_SCOPE":
        return {
            "intent": intent,
            "action": "RESPOND",
            "response_mode": "out_of_scope",
            "request_kind": "general",
            "search_query": None,
        }
    return {
        "intent": intent,
        "action": "RESPOND",
        "response_mode": "general",
        "request_kind": "general",
        "search_query": None,
    }


def heuristic_extract_profile(text: str) -> dict[str, Any]:
    profile: dict[str, Any] = {}

    age_match = re.search(r"(\d{2})\s*살|(\d{2})\s*세", text)
    if age_match:
        profile["age"] = int(next(group for group in age_match.groups() if group))

    if region := user_region_reference(text):
        profile["region"] = region

    if any(keyword in text for keyword in JOB_SEEKING_KEYWORDS):
        profile["employment_status"] = "unemployed_seeking_job"
    elif any(keyword in text for keyword in EMPLOYED_KEYWORDS):
        profile["employment_status"] = "employed"
    elif any(keyword in text for keyword in STUDENT_KEYWORDS):
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

    if any(keyword in text for keyword in ENTREPRENEUR_KEYWORDS):
        profile["is_entrepreneur"] = True

    if "사업자 등록" in text:
        profile["has_registered_business"] = not any(
            negative in text for negative in ["안 했", "안했", "없", "아직", "미등록"]
        )

    matched_fields = [
        field for field, keywords in INTEREST_KEYWORDS.items() if any(keyword in text for keyword in keywords)
    ]
    if matched_fields:
        profile["interest_fields"] = matched_fields
        profile["desired_job"] = matched_fields[0]

    for topic, keywords in POLICY_TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            profile["policy_topic"] = topic
            break

    desired_job_match = re.search(r"([가-힣A-Za-z0-9+# ]{2,20})\s*(쪽|분야|직무)로", text)
    if desired_job_match and not profile.get("desired_job"):
        profile["desired_job"] = desired_job_match.group(1).strip()

    if "지원금" in text:
        profile["preferred_support_type"] = "지원금"
    elif any(keyword in text for keyword in TRAINING_KEYWORDS):
        profile["preferred_support_type"] = "훈련"
    elif any(keyword in text for keyword in RECRUITMENT_KEYWORDS):
        profile["preferred_support_type"] = "채용"

    return profile


def general_reply(query: str) -> str:
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
