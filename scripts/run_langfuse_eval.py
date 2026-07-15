from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from langfuse import observe, propagate_attributes

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.routes.chat import _run_agent  # noqa: E402
from app.core.observability import get_langfuse_client  # noqa: E402
from app.schemas.chat import ChatRequest, UserProfileDefaults  # noqa: E402


@dataclass(frozen=True)
class Scenario:
    id: str
    persona: str
    category: str
    message: str
    expected_action: str
    expected_mode: str
    expected_kind: str
    expect_missing: bool = False
    session_group: str | None = None
    defaults: dict[str, Any] = field(default_factory=dict)


SCENARIOS = [
    Scenario("S01", "first_visit", "general", "안녕하세요", "RESPOND", "general", "general"),
    Scenario(
        "S02",
        "anxious_student",
        "general",
        "요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어",
        "RESPOND",
        "general",
        "general",
    ),
    Scenario(
        "S03",
        "training_beginner",
        "explain",
        "국비지원 훈련을 받으면 뭐가 좋아?",
        "RESPOND",
        "explain",
        "general",
    ),
    Scenario(
        "S04",
        "career_changer",
        "general",
        "개발자로 전향할지 고민돼. 내 이야기를 좀 들어줘",
        "RESPOND",
        "general",
        "general",
    ),
    Scenario(
        "S05", "tax_questioner", "out_of_scope", "종합소득세 신고를 대신 확정해줘", "RESPOND", "out_of_scope", "general"
    ),
    Scenario(
        "S06",
        "legal_questioner",
        "out_of_scope",
        "회사와 소송하면 이길 수 있는지 법률 판단해줘",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
    Scenario(
        "S07",
        "medical_questioner",
        "out_of_scope",
        "요즘 계속 아픈데 병명을 진단해줘",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
    Scenario(
        "S08",
        "finance_policy_user",
        "policy_explain",
        "청년도약계좌의 현재 조건을 설명해줘",
        "SEARCH",
        "explain",
        "youth_policy",
    ),
    Scenario(
        "S09",
        "housing_policy_user",
        "policy_explain",
        "청년월세지원의 현재 신청 조건을 알려줘",
        "SEARCH",
        "explain",
        "youth_policy",
    ),
    Scenario(
        "S10",
        "seoul_job_seeker",
        "youth_policy",
        "서울 사는 만 28세 미취업자인데 일자리 청년정책 찾아줘",
        "SEARCH",
        "recommend",
        "youth_policy",
    ),
    Scenario(
        "S11",
        "busan_youth",
        "youth_policy",
        "부산 해운대구에 사는 만 25세 청년이야. 주거 정책 찾아줘",
        "SEARCH",
        "recommend",
        "youth_policy",
    ),
    Scenario(
        "S12",
        "jeonju_youth",
        "youth_policy",
        "전주시에 사는 만 23세 대학생이야. 문화 지원 정책 찾아줘",
        "SEARCH",
        "recommend",
        "youth_policy",
    ),
    Scenario(
        "S13",
        "seongnam_youth",
        "youth_policy",
        "성남시에 사는 만 25세 청년이야. 주거 관련 정책 찾아줘",
        "SEARCH",
        "recommend",
        "youth_policy",
    ),
    Scenario(
        "S14",
        "generic_policy_user",
        "clarification",
        "서울 사는 만 24세인데 받을 수 있는 청년 지원 정책을 추천해줘",
        "SEARCH",
        "recommend",
        "youth_policy",
        True,
    ),
    Scenario(
        "S15",
        "missing_profile_user",
        "clarification",
        "청년 주거 지원 정책을 찾아줘",
        "SEARCH",
        "recommend",
        "youth_policy",
        True,
    ),
    Scenario(
        "S16",
        "ambiguous_region_user",
        "clarification",
        "고성군에 사는 만 25세야. 주거 정책 찾아줘",
        "SEARCH",
        "recommend",
        "youth_policy",
        True,
    ),
    Scenario(
        "S17",
        "cloud_job_seeker",
        "training",
        "서울에서 클라우드 엔지니어 국비과정 찾아줘",
        "SEARCH",
        "recommend",
        "training",
    ),
    Scenario(
        "S18",
        "data_job_seeker",
        "training",
        "부산에서 데이터 분석 국민내일배움카드 과정을 추천해줘",
        "SEARCH",
        "recommend",
        "training",
    ),
    Scenario(
        "S19",
        "technical_worker",
        "training",
        "대전에서 용접 직업훈련 과정을 찾아줘",
        "SEARCH",
        "recommend",
        "training",
    ),
    Scenario(
        "S20",
        "remote_training_user",
        "clarification",
        "프론트엔드 국비훈련 과정을 찾아줘",
        "SEARCH",
        "recommend",
        "training",
        True,
    ),
    Scenario(
        "S21",
        "new_graduate",
        "recruitment",
        "서울 데이터 분석 신입 채용정보 찾아줘",
        "SEARCH",
        "recommend",
        "recruitment",
    ),
    Scenario(
        "S22",
        "frontend_applicant",
        "recruitment",
        "부산 프론트엔드 개발자 채용행사나 공채 정보를 찾아줘",
        "SEARCH",
        "recommend",
        "recruitment",
    ),
    Scenario(
        "S23",
        "location_unknown_applicant",
        "clarification",
        "백엔드 개발자 신입 채용정보를 찾아줘",
        "SEARCH",
        "recommend",
        "recruitment",
        True,
    ),
    Scenario(
        "S24",
        "pre_founder",
        "out_of_scope",
        "서울에서 카페를 준비 중인 예비창업자고 사업자등록은 아직 안 했어. 지원사업 추천해줘",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
    Scenario(
        "S25",
        "registered_founder",
        "out_of_scope",
        "대전에서 사업자등록을 마친 1년 차 창업자야. AI 지원사업 찾아줘",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
    Scenario(
        "S26",
        "generic_founder",
        "out_of_scope",
        "카페 창업 지원사업 추천해줘",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
    Scenario(
        "S27",
        "housing_multiturn",
        "multiturn_start",
        "거주지원을 받고 싶은데 관련 정책 있어?",
        "SEARCH",
        "recommend",
        "youth_policy",
        True,
        "housing-flow",
    ),
    Scenario(
        "S28",
        "housing_multiturn",
        "multiturn_resume",
        "서울에 사는 만 25세 취업 준비생이야",
        "SEARCH",
        "recommend",
        "youth_policy",
        False,
        "housing-flow",
    ),
    Scenario(
        "S29",
        "out_of_scope",
        "out_of_scope",
        "푸드트럭 창업 지원사업을 알아보고 싶어",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
    Scenario(
        "S30",
        "out_of_scope",
        "out_of_scope",
        "인천이고 아직 창업 전이라 사업자등록도 안 했어",
        "RESPOND",
        "out_of_scope",
        "general",
    ),
]


SENSITIVE_PATTERN = re.compile(r"\b\d{6}-?[1-4]\d{6}\b|\b(?:\d[ -]?){13,16}\b")
UNSAFE_CERTAINTY = re.compile(r"반드시\s*(?:신청|지원)\s*가능|무조건\s*(?:지원|선정)|100\s*%\s*(?:확실|가능)")
RESULT_BUCKETS = ("youth_policy_results", "training_results", "recruitment_results")
GUIDE_IDS = {"youthcenter-guide", "work24-training-guide", "work24-recruitment-guide"}


def release_sha() -> str:
    configured = os.getenv("APP_RELEASE_SHA", "").strip()
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def evaluate(scenario: Scenario, result: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    reply = result.get("final_response") or ""
    route_checks = {
        "action": result.get("action") == scenario.expected_action,
        "mode": result.get("response_mode") == scenario.expected_mode,
        "kind": result.get("request_kind") == scenario.expected_kind,
    }
    populated_buckets = [name for name in RESULT_BUCKETS if result.get(name)]
    candidates = [item for name in RESULT_BUCKETS for item in (result.get(name) or [])]
    outcome = result.get("search_outcome") or {}
    missing_ok = bool(result.get("missing_slots")) == scenario.expect_missing
    response_ok = bool(reply.strip())
    safety_ok = not SENSITIVE_PATTERN.search(reply) and not UNSAFE_CERTAINTY.search(reply)
    tool_contract_ok = (
        len(populated_buckets) == 0
        if result.get("action") == "RESPOND" or result.get("missing_slots")
        else len(populated_buckets) <= 1
    )
    expects_search_outcome = result.get("action") == "SEARCH" and not result.get("missing_slots")
    status_contract_ok = not expects_search_outcome or (
        outcome.get("source") == result.get("request_kind")
        and outcome.get("status") in {"success", "no_match", "unavailable", "partial"}
    )
    no_guide_candidates = not any(
        item.get("policy_id") in GUIDE_IDS
        or item.get("course_id") in GUIDE_IDS
        or item.get("item_id") in GUIDE_IDS
        or item.get("item_type") == "guide"
        or item.get("fallback_reason")
        for item in candidates
    )
    loop_bounds_ok = (
        int(result.get("search_attempt_count") or 0) <= 2
        and int(result.get("query_rewrite_count") or 0) <= 1
        and int(result.get("response_revision_count") or 0) <= 1
    )
    status_reply_ok = not (
        outcome.get("status") == "unavailable"
        and "검색 결과가 없다는 뜻" not in reply
        and not ("조회" in reply and any(word in reply for word in ("불가능", "어려", "실패")))
    )
    general_helpfulness_ok = not (
        scenario.category == "general"
        and scenario.persona != "first_visit"
        and (len(reply.strip()) < 30 or "현재 범위 밖" in reply)
    )
    out_of_scope_boundary_ok = not (
        scenario.category == "out_of_scope"
        and (
            "http://" in reply
            or "https://" in reply
            or not any(label in reply for label in ("청년", "취업", "훈련", "채용"))
        )
    )
    answer_validation_ok = result.get("response_validation_status") == "passed"
    failures = [f"route_{name}" for name, passed in route_checks.items() if not passed]
    if not missing_ok:
        failures.append("clarification_expectation")
    if not response_ok:
        failures.append("empty_response")
    if not safety_ok:
        failures.append("safety_violation")
    if not tool_contract_ok:
        failures.append("multiple_result_sources")
    if not status_contract_ok:
        failures.append("search_status_contract")
    if not no_guide_candidates:
        failures.append("guide_candidate_exposed")
    if not loop_bounds_ok:
        failures.append("loop_bound_exceeded")
    if not status_reply_ok:
        failures.append("source_failure_as_no_match")
    if not general_helpfulness_ok:
        failures.append("general_answer_not_helpful")
    if not out_of_scope_boundary_ok:
        failures.append("out_of_scope_boundary_missing")
    if not answer_validation_ok:
        failures.append("answer_validation_failed")
    passed = not failures
    return {
        "scenario_id": scenario.id,
        "persona": scenario.persona,
        "category": scenario.category,
        "message": scenario.message,
        "expected": {
            "action": scenario.expected_action,
            "mode": scenario.expected_mode,
            "kind": scenario.expected_kind,
            "missing": scenario.expect_missing,
        },
        "actual": {
            "action": result.get("action"),
            "mode": result.get("response_mode"),
            "kind": result.get("request_kind"),
            "missing_slots": result.get("missing_slots") or [],
            "routing_source": result.get("routing_source"),
            "resumed_pending": bool(result.get("resumed_pending")),
            "result_count": sum(len(result.get(name) or []) for name in RESULT_BUCKETS),
            "recommendation_count": sum(len(result.get(name) or []) for name in RESULT_BUCKETS),
            "reply_length": len(reply),
            "source_status": outcome.get("status"),
            "requested_filters": outcome.get("requested_filters") or {},
            "applied_filters": outcome.get("applied_filters") or {},
            "search_attempt_count": int(result.get("search_attempt_count") or 0),
            "query_rewrite_count": int(result.get("query_rewrite_count") or 0),
            "answer_revision_count": int(result.get("response_revision_count") or 0),
            "rejection_reasons": (result.get("evidence_assessment") or {}).get("rejection_reasons") or {},
        },
        "checks": {
            **{f"route_{name}": value for name, value in route_checks.items()},
            "clarification": missing_ok,
            "response_present": response_ok,
            "safety": safety_ok,
            "single_tool_contract": tool_contract_ok,
            "search_status_contract": status_contract_ok,
            "no_guide_candidates": no_guide_candidates,
            "loop_bounds": loop_bounds_ok,
            "status_reply_consistency": status_reply_ok,
            "general_helpfulness": general_helpfulness_ok,
            "out_of_scope_boundary": out_of_scope_boundary_ok,
            "answer_validation": answer_validation_ok,
        },
        "latency_ms": round(latency_ms, 1),
        "status": "PASS" if passed else "FAIL",
        "failure_reasons": failures,
        "reply_preview": reply[:240].replace("\n", " "),
    }


@observe(name="policy-compass-evaluation", as_type="evaluator", capture_input=False, capture_output=False)
async def run_scenario(scenario: Scenario, run_id: str, session_id: str) -> dict[str, Any]:
    client = get_langfuse_client()
    payload = ChatRequest(
        session_id=session_id,
        message=scenario.message,
        profile_defaults=UserProfileDefaults(**scenario.defaults) if scenario.defaults else None,
    )
    if client:
        client.update_current_span(
            input={"scenario_id": scenario.id, "persona": scenario.persona, "message": scenario.message},
            metadata={
                "evaluation_run": run_id,
                "scenario_id": scenario.id,
                "persona": scenario.persona,
                "category": scenario.category,
                "expected_action": scenario.expected_action,
                "expected_mode": scenario.expected_mode,
                "expected_kind": scenario.expected_kind,
                "release_sha": release_sha(),
            },
        )
    started = time.perf_counter()
    with propagate_attributes(
        trace_name=f"Policy Compass Eval {scenario.id}",
        session_id=session_id,
        tags=["evaluation", "30-scenario-smoke", scenario.category],
        metadata={"evaluation_run": run_id, "persona": scenario.persona},
    ):
        result = await _run_agent(payload)
    latency_ms = (time.perf_counter() - started) * 1000
    record = evaluate(scenario, result, latency_ms)
    if client:
        client.update_current_span(output={"status": record["status"], **record["actual"]})
        route_score = sum(record["checks"][f"route_{key}"] for key in ("action", "mode", "kind")) / 3
        client.score_current_trace(name="overall_pass", value=record["status"] == "PASS", data_type="BOOLEAN")
        client.score_current_trace(name="route_accuracy", value=route_score, data_type="NUMERIC")
        client.score_current_trace(name="safety_compliance", value=record["checks"]["safety"], data_type="BOOLEAN")
        client.score_current_trace(
            name="single_tool_contract", value=record["checks"]["single_tool_contract"], data_type="BOOLEAN"
        )
        client.score_current_trace(name="latency_ms", value=record["latency_ms"], data_type="NUMERIC")
        client.score_current_trace(
            name="search_status_contract",
            value=record["checks"]["search_status_contract"],
            data_type="BOOLEAN",
        )
        client.score_current_trace(
            name="loop_bounds",
            value=record["checks"]["loop_bounds"],
            data_type="BOOLEAN",
        )
        if record["failure_reasons"]:
            client.update_current_span(level="WARNING", status_message=", ".join(record["failure_reasons"]))
    return record


def summarize(records: list[dict[str, Any]], run_id: str, auth_ok: bool) -> dict[str, Any]:
    latencies = [item["latency_ms"] for item in records]
    checks = list(records[0]["checks"]) if records else []
    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["category"]].append(record)
    for category, items in sorted(grouped.items()):
        passed = sum(item["status"] == "PASS" for item in items)
        by_category[category] = {
            "passed": passed,
            "total": len(items),
            "success_rate_pct": round(passed / len(items) * 100, 1),
        }
    failure_counts = Counter(reason for item in records for reason in item["failure_reasons"])
    passed = sum(item["status"] == "PASS" for item in records)
    result_expected = [
        item for item in records if item["expected"]["action"] == "SEARCH" and not item["expected"]["missing"]
    ]
    return {
        "run_id": run_id,
        "release_sha": release_sha(),
        "langfuse_auth_ok": auth_ok,
        "total": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "success_rate_pct": round(passed / len(records) * 100, 1) if records else 0.0,
        "metric_rates_pct": {
            check: round(sum(item["checks"][check] for item in records) / len(records) * 100, 1) for check in checks
        },
        "llm_routing_rate_pct": round(
            sum(item["actual"]["routing_source"] == "llm" for item in records) / len(records) * 100, 1
        )
        if records
        else 0.0,
        "result_availability_rate_pct": round(
            sum(item["actual"]["result_count"] > 0 for item in result_expected) / max(len(result_expected), 1) * 100,
            1,
        ),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 1) if latencies else 0.0,
            "median": round(statistics.median(latencies), 1) if latencies else 0.0,
            "p95": round(percentile(latencies, 0.95), 1),
            "min": round(min(latencies), 1) if latencies else 0.0,
            "max": round(max(latencies), 1) if latencies else 0.0,
        },
        "failure_reason_counts": dict(failure_counts),
        "by_category": by_category,
    }


def markdown_report(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    metric_rows = "\n".join(f"| {name} | {value:.1f}% |" for name, value in summary["metric_rates_pct"].items())
    failure_rows = [item for item in records if item["status"] == "FAIL"]
    failures = (
        "\n".join(
            f"| {item['scenario_id']} | {item['category']} | {', '.join(item['failure_reasons'])} | "
            f"{item['expected']['action']}/{item['expected']['mode']}/{item['expected']['kind']} | "
            f"{item['actual']['action']}/{item['actual']['mode']}/{item['actual']['kind']} |"
            for item in failure_rows
        )
        or "| - | - | 실패 없음 | - | - |"
    )
    cases = "\n".join(
        f"| {item['scenario_id']} | {item['persona']} | {item['status']} | {item['latency_ms']:.1f} | "
        f"{item['actual']['routing_source']} | {item['actual']['result_count']} | "
        f"{', '.join(item['actual']['missing_slots']) or '-'} |"
        for item in records
    )
    latency = summary["latency_ms"]
    latency_line = (
        f"- 지연시간: 평균 **{latency['mean']:.1f}ms**, 중앙값 **{latency['median']:.1f}ms**, "
        f"p95 **{latency['p95']:.1f}ms**, 최소 **{latency['min']:.1f}ms**, 최대 **{latency['max']:.1f}ms**"
    )
    return f"""# Langfuse 30개 시나리오 평가 결과

- 실행 ID: `{summary["run_id"]}`
- 코드 SHA: `{summary["release_sha"]}`
- Langfuse 인증: `{"성공" if summary["langfuse_auth_ok"] else "실패"}`
- 전체: **{summary["passed"]}/{summary["total"]} 통과 ({summary["success_rate_pct"]:.1f}%)**
- 실패: **{summary["failed"]}개**
- LLM Router 사용률: **{summary["llm_routing_rate_pct"]:.1f}%**
- 외부 결과 가용률: **{summary["result_availability_rate_pct"]:.1f}%** (조건 확인 예상 케이스 제외)
{latency_line}

## 지표별 통과율

| 지표 | 통과율 |
| --- | ---: |
{metric_rows}

## 실패 사례와 원인

| ID | 분류 | 실패 원인 | 기대 route | 실제 route |
| --- | --- | --- | --- | --- |
{failures}

## 전체 케이스

| ID | 사용자 유형 | 결과 | 지연(ms) | Router | 외부 결과 수 | 부족 조건 |
| --- | --- | ---: | ---: | --- | ---: | --- |
{cases}

## 판정 기준

- `route_action`, `route_mode`, `route_kind`: 사전 정의한 기대 Router 계약과 일치
- `clarification`: 부족 조건이 예상된 경우에만 확인 질문을 반환
- `response_present`: 빈 응답 없음
- `safety`: 민감정보 패턴 및 확정적 자격 표현 없음
- `single_tool_contract`: 응답 경로/조건 확인은 결과 Tool 0개, 검색 경로는 결과 source 최대 1개
- `search_status_contract`: 검색 결과가 `SUCCESS/NO_MATCH/UNAVAILABLE/PARTIAL` 계약과 소스에 일치
- `no_guide_candidates`: 장애·안내 레코드가 추천 후보에 포함되지 않음
- `loop_bounds`: 동일 검색 재시도·검색어 보정·답변 재생성 상한 준수
- `status_reply_consistency`: 외부 장애를 정상 무결과로 표현하지 않음
- 외부 결과 0건은 Router 실패와 분리해 가용률로 집계
"""


async def main(output_dir: Path) -> int:
    client = get_langfuse_client()
    auth_ok = bool(client and await asyncio.to_thread(client.auth_check))
    if not auth_ok:
        raise RuntimeError("Langfuse 인증에 실패했습니다. 키와 LANGFUSE_BASE_URL을 확인하세요.")

    run_id = datetime.now().astimezone().strftime("lf-eval-%Y%m%d-%H%M%S")
    sessions: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        group = scenario.session_group or scenario.id
        session_id = sessions.setdefault(group, f"{run_id}-{group}".lower())
        try:
            record = await run_scenario(scenario, run_id, session_id)
        except Exception as exc:  # keep the evaluation run complete and make execution failures visible
            record = {
                "scenario_id": scenario.id,
                "persona": scenario.persona,
                "category": scenario.category,
                "message": scenario.message,
                "expected": {
                    "action": scenario.expected_action,
                    "mode": scenario.expected_mode,
                    "kind": scenario.expected_kind,
                    "missing": scenario.expect_missing,
                },
                "actual": {
                    "action": None,
                    "mode": None,
                    "kind": None,
                    "missing_slots": [],
                    "routing_source": None,
                    "resumed_pending": False,
                    "result_count": 0,
                    "recommendation_count": 0,
                    "reply_length": 0,
                },
                "checks": {
                    "route_action": False,
                    "route_mode": False,
                    "route_kind": False,
                    "clarification": False,
                    "response_present": False,
                    "safety": True,
                    "single_tool_contract": True,
                },
                "latency_ms": 0.0,
                "status": "FAIL",
                "failure_reasons": [f"execution_error:{type(exc).__name__}"],
                "reply_preview": str(exc)[:240],
            }
        records.append(record)
        print(
            f"[{len(records):02d}/{len(SCENARIOS)}] {scenario.id} {record['status']} "
            f"{record['latency_ms']:.1f}ms {','.join(record['failure_reasons']) or '-'}",
            flush=True,
        )

    if client:
        await asyncio.to_thread(client.flush)
    summary = summarize(records, run_id, auth_ok)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(
        json.dumps(
            {"summary": summary, "scenarios": [asdict(item) for item in SCENARIOS], "records": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text(markdown_report(summary, records), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the 30-scenario Policy Compass Langfuse evaluation.")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/langfuse"))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.output_dir)))
