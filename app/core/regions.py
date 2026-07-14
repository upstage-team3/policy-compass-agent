"""공공정책 데이터 소스 사이의 지역 표현을 한 곳에서 정규화한다.

온통청년은 법정시군구코드, 기업마당은 제한된 시·도 해시태그를 사용한다.
사용자가 입력한 지역명은 그대로 보존하되 외부 API 호출과 후보 비교에는 이
모듈이 반환하는 표준 시·도명과 코드를 사용한다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Literal

from app.core.administrative_regions import MUNICIPALITY_ROWS

RegionMatchScope = Literal["exact", "nationwide", "mismatch", "unknown"]

SIDO_ORDER = (
    "서울",
    "전남광주",
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
)

SIDO_CODE_PREFIXES = {
    "서울": "11",
    "전남광주": "12",
    "부산": "26",
    "대구": "27",
    "인천": "28",
    "광주": "29",
    "대전": "30",
    "울산": "31",
    "세종": "36",
    "경기": "41",
    "충북": "43",
    "충남": "44",
    "전남": "46",
    "경북": "47",
    "경남": "48",
    "제주": "50",
    "강원": "51",
    "전북": "52",
}

# 기업마당은 광주와 전남을 하나의 공식 해시태그로 제공한다.
BIZINFO_REGION_TAGS = (
    "서울",
    "부산",
    "대구",
    "인천",
    "전남광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "경북",
    "경남",
    "제주",
)
_BIZINFO_SPLIT_REGION_TAGS = frozenset(
    {
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
    }
)

# 도로 이동 거리가 아니라 시·도 대표 좌표 간 직선거리다. 전국 시군구에
# 동일한 동작을 보장하고, 별도 좌표가 검증된 일부 지역만 더 세밀하게 쓴다.
SIDO_CENTERS = {
    "서울": (37.5665, 126.9780),
    "전남광주": (34.9878, 126.6574),
    "부산": (35.1796, 129.0756),
    "대구": (35.8714, 128.6014),
    "인천": (37.4563, 126.7052),
    "광주": (35.1595, 126.8526),
    "대전": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114),
    "세종": (36.4800, 127.2890),
    "경기": (37.2749, 127.0095),
    "강원": (37.8854, 127.7298),
    "충북": (36.6357, 127.4915),
    "충남": (36.6588, 126.6728),
    "전북": (35.8203, 127.1088),
    "전남": (34.8161, 126.4629),
    "경북": (36.5760, 128.5056),
    "경남": (35.2383, 128.6924),
    "제주": (33.4996, 126.5312),
}

_SIDO_ALIASES = {
    "서울": "서울",
    "서울시": "서울",
    "서울특별시": "서울",
    "전남광주": "전남광주",
    "전남광주통합특별시": "전남광주",
    "부산": "부산",
    "부산시": "부산",
    "부산광역시": "부산",
    "대구": "대구",
    "대구시": "대구",
    "대구광역시": "대구",
    "인천": "인천",
    "인천시": "인천",
    "인천광역시": "인천",
    "광주": "광주",
    "광주광역시": "광주",
    "대전": "대전",
    "대전시": "대전",
    "대전광역시": "대전",
    "울산": "울산",
    "울산시": "울산",
    "울산광역시": "울산",
    "세종": "세종",
    "세종시": "세종",
    "세종특별자치시": "세종",
    "경기": "경기",
    "경기도": "경기",
    "강원": "강원",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충북": "충북",
    "충청북도": "충북",
    "충남": "충남",
    "충청남도": "충남",
    "전북": "전북",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전남": "전남",
    "전라남도": "전남",
    "경북": "경북",
    "경상북도": "경북",
    "경남": "경남",
    "경상남도": "경남",
    "제주": "제주",
    "제주도": "제주",
    "제주특별자치도": "제주",
}

# 지방자치단체 기관명 판정에는 짧은 지명보다 공식 명칭만 사용한다.
_LOCAL_AUTHORITY_ALIASES = {
    alias: sido
    for alias, sido in _SIDO_ALIASES.items()
    if alias.endswith(("특별시", "광역시", "특별자치도", "경기도", "도")) and alias not in {"제주도", "강원도"}
}

_EQUIVALENT_SIDO_GROUP = frozenset({"전남광주", "광주", "전남"})
_SINGLE_MUNICIPALITY_SIDO_CODES = {"세종": "36110"}


@dataclass(frozen=True)
class RegionResolution:
    raw: str
    sido: str
    latitude: float
    longitude: float
    sigungu: str | None = None
    youth_code: str | None = None


@dataclass(frozen=True)
class _Municipality:
    sido: str
    name: str
    youth_code: str
    latitude: float
    longitude: float


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


_PRECISE_MUNICIPALITY_CENTERS = {
    "41130": (37.4200, 127.1265),
    "41131": (37.4504, 127.1456),
    "41133": (37.4305, 127.1373),
    "41135": (37.3827, 127.1189),
    "28237": (37.5070, 126.7218),
    "44270": (36.8899, 126.6458),
}


def _municipality_from_row(sido: str, youth_code: str, name: str) -> _Municipality:
    latitude, longitude = _PRECISE_MUNICIPALITY_CENTERS.get(youth_code, SIDO_CENTERS[sido])
    return _Municipality(sido, name, youth_code, latitude, longitude)


_MUNICIPALITIES = tuple(_municipality_from_row(*row) for row in MUNICIPALITY_ROWS)
_MUNICIPALITY_BY_CODE = {item.youth_code: item for item in _MUNICIPALITIES}


def _municipality_aliases(item: _Municipality) -> tuple[set[str], set[str]]:
    full_name = _compact(item.name)
    leaf_name = _compact(item.name.split()[-1])
    exact_aliases = {full_name, leaf_name}
    if len(leaf_name) > 2 and leaf_name.endswith(("시", "군", "구")):
        exact_aliases.add(leaf_name[:-1])
    return exact_aliases, {full_name, leaf_name}


def _build_municipality_indexes() -> tuple[
    dict[str, tuple[_Municipality, ...]],
    dict[str, tuple[_Municipality, ...]],
]:
    exact: dict[str, list[_Municipality]] = defaultdict(list)
    contained: dict[str, list[_Municipality]] = defaultdict(list)
    for item in _MUNICIPALITIES:
        exact_aliases, contained_aliases = _municipality_aliases(item)
        for alias in exact_aliases:
            if item not in exact[alias]:
                exact[alias].append(item)
        for alias in contained_aliases:
            if item not in contained[alias]:
                contained[alias].append(item)
    return (
        {alias: tuple(items) for alias, items in exact.items()},
        {alias: tuple(items) for alias, items in contained.items()},
    )


_EXACT_MUNICIPALITY_INDEX, _CONTAINED_MUNICIPALITY_INDEX = _build_municipality_indexes()
_CONTAINED_ALIASES = tuple(sorted(_CONTAINED_MUNICIPALITY_INDEX, key=len, reverse=True))


def _formal_sido_hint(compact: str) -> str | None:
    matches = [(len(alias), sido) for alias, sido in _LOCAL_AUTHORITY_ALIASES.items() if alias in compact]
    return max(matches, default=(0, None))[1]


def _short_sido_hint(compact: str) -> str | None:
    matches = [(len(alias), sido) for alias, sido in _SIDO_ALIASES.items() if compact.startswith(alias)]
    return max(matches, default=(0, None))[1]


def _any_sido_hint(compact: str) -> str | None:
    matches = [(len(alias), sido) for alias, sido in _SIDO_ALIASES.items() if alias in compact]
    return max(matches, default=(0, None))[1]


def _select_municipality(
    candidates: tuple[_Municipality, ...] | list[_Municipality],
    sido_hint: str | None,
) -> _Municipality | None:
    filtered = [item for item in candidates if sido_hint is None or item.sido == sido_hint]
    if len(filtered) == 1:
        return filtered[0]
    if (
        filtered
        and {item.sido for item in filtered}.issubset(_EQUIVALENT_SIDO_GROUP)
        and len({item.name for item in filtered}) == 1
    ):
        return next(
            (item for item in filtered if item.sido == "전남광주"),
            filtered[0],
        )
    return None


def _best_contained_match(compact: str) -> tuple[str | None, tuple[_Municipality, ...]]:
    for alias in _CONTAINED_ALIASES:
        if alias in compact:
            return alias, _CONTAINED_MUNICIPALITY_INDEX[alias]
    return None, ()


def _municipality_resolution(raw: str, item: _Municipality) -> RegionResolution:
    return RegionResolution(
        raw,
        item.sido,
        item.latitude,
        item.longitude,
        sigungu=item.name,
        youth_code=item.youth_code,
    )


def _sido_resolution(raw: str, sido: str) -> RegionResolution:
    latitude, longitude = SIDO_CENTERS[sido]
    return RegionResolution(
        raw,
        sido,
        latitude,
        longitude,
        youth_code=_SINGLE_MUNICIPALITY_SIDO_CODES.get(sido),
    )


def resolve_region(value: str | None) -> RegionResolution | None:
    """전국 현존 시·군·구 이름을 표준 시·도와 5자리 코드로 변환한다.

    중구·고성군처럼 여러 시·도에 같은 이름이 있으면 시·도 없이 추정하지 않는다.
    """

    if not value:
        return None
    compact = _compact(value)
    if not compact:
        return None

    if compact in _SIDO_ALIASES:
        return _sido_resolution(value, _SIDO_ALIASES[compact])

    exact_candidates = _EXACT_MUNICIPALITY_INDEX.get(compact, ())
    exact_match = _select_municipality(exact_candidates, None)
    if exact_match:
        return _municipality_resolution(value, exact_match)

    formal_hint = _formal_sido_hint(compact)
    matched_alias, contained_candidates = _best_contained_match(compact)
    if contained_candidates:
        if formal_hint:
            formal_match = _select_municipality(contained_candidates, formal_hint)
            return _municipality_resolution(value, formal_match) if formal_match else None

        short_hint = _short_sido_hint(compact)
        if short_hint:
            hinted_match = _select_municipality(contained_candidates, short_hint)
            if hinted_match:
                return _municipality_resolution(value, hinted_match)

        unique_match = _select_municipality(contained_candidates, None)
        if unique_match:
            if (
                short_hint
                and short_hint != unique_match.sido
                and matched_alias
                and not compact.startswith(matched_alias)
            ):
                return None
            return _municipality_resolution(value, unique_match)
        return None

    sido_hint = formal_hint or _short_sido_hint(compact) or _any_sido_hint(compact)
    return _sido_resolution(value, sido_hint) if sido_hint else None


def user_region_reference(value: str | None) -> str | None:
    """사용자가 실제로 말한 지역을 추정 없이 표준 검색 문자열로 만든다."""

    resolved = resolve_region(value)
    if resolved:
        return f"{resolved.sido} {resolved.sigungu}" if resolved.sigungu else resolved.sido
    if not value:
        return None

    matched_alias, candidates = _best_contained_match(_compact(value))
    return matched_alias if candidates else None


def _equivalent_sidos(sido: str) -> frozenset[str]:
    return _EQUIVALENT_SIDO_GROUP if sido in _EQUIVALENT_SIDO_GROUP else frozenset({sido})


def bizinfo_region_tag(value: str | None) -> str | None:
    resolved = resolve_region(value)
    if not resolved:
        return None
    if resolved.sido in _EQUIVALENT_SIDO_GROUP:
        return "전남광주"
    return resolved.sido


def normalize_bizinfo_regions(hashtags: str | None) -> list[str]:
    """기업마당 공식 해시태그를 앱의 시·도 목록으로 변환한다."""

    tokens = {token.strip().lstrip("#") for token in (hashtags or "").split(",") if token.strip().lstrip("#")}
    official = tokens.intersection(BIZINFO_REGION_TAGS)
    if set(BIZINFO_REGION_TAGS).issubset(official) or _BIZINFO_SPLIT_REGION_TAGS.issubset(tokens):
        return ["전국"]

    matched: set[str] = set()
    for token in tokens:
        if token == "전남광주":
            matched.update({"광주", "전남"})
            continue
        resolved = resolve_region(token)
        if resolved and (token in BIZINFO_REGION_TAGS or token in _SIDO_ALIASES):
            matched.add(resolved.sido)
    return [sido for sido in SIDO_ORDER if sido in matched]


_BIZINFO_LOCAL_CONSTRAINT_MARKERS = (
    "소재",
    "소재지",
    "본점",
    "본사",
    "사업장",
    "이전",
    "전입",
    "설립",
    "관내",
    "도내",
    "지역기업",
    "지역창업기업",
    "지역스타트업",
    "지역소상공인",
)
_BIZINFO_RELOCATION_MARKERS = ("이전", "전입", "설립")
_BIZINFO_UNRESTRICTED_MARKERS = ("지역제한없음", "지역무관")


def _referenced_sidos(value: str | None) -> set[str]:
    compact = _compact(value or "")
    if not compact:
        return set()

    matched: set[str] = set()
    for alias, sido in _SIDO_ALIASES.items():
        if alias in compact:
            matched.add(sido)

    formal_hint = _formal_sido_hint(compact)
    for alias in _CONTAINED_ALIASES:
        if alias not in compact:
            continue
        municipality = _select_municipality(_CONTAINED_MUNICIPALITY_INDEX[alias], formal_hint)
        if municipality:
            matched.add(municipality.sido)
    return matched


def _bizinfo_local_restriction_regions(
    title: str | None,
    summary: str | None,
    agency: str | None,
) -> list[str]:
    """공고 본문의 소재지·이전 조건에 명시된 지역만 보수적으로 추출한다."""

    compact_summary = _compact(re.sub(r"<[^>]+>", " ", summary or ""))
    if not compact_summary:
        return []

    has_relocation_condition = any(marker in compact_summary for marker in _BIZINFO_RELOCATION_MARKERS)
    if any(marker in compact_summary for marker in _BIZINFO_UNRESTRICTED_MARKERS) and not has_relocation_condition:
        return []

    matched: set[str] = set()
    for marker in _BIZINFO_LOCAL_CONSTRAINT_MARKERS:
        start = 0
        while (position := compact_summary.find(marker, start)) >= 0:
            window = compact_summary[max(0, position - 80) : position + len(marker) + 80]
            matched.update(_referenced_sidos(window))
            start = position + len(marker)

    if not matched and any(marker in compact_summary for marker in _BIZINFO_LOCAL_CONSTRAINT_MARKERS):
        context_regions = _referenced_sidos(" ".join(value for value in (title, agency) if value))
        if len(context_regions) == 1:
            matched.update(context_regions)

    return [sido for sido in SIDO_ORDER if sido in matched]


def bizinfo_effective_regions(
    hashtags: str | None,
    *,
    title: str | None = None,
    summary: str | None = None,
    agency: str | None = None,
) -> list[str]:
    """기업마당 태그와 공고의 명시적 소재지 조건을 교차 검증한다.

    기업마당은 지역 제한이 있는 일부 지자체 공고에도 모든 지역 태그를
    제공한다. 본문에 소재지·이전 조건이 명시돼 있으면 그 지역을 우선하고,
    근거가 없을 때만 공식 태그의 전국 판정을 유지한다.
    """

    compact_summary = _compact(re.sub(r"<[^>]+>", " ", summary or ""))
    has_relocation_condition = any(marker in compact_summary for marker in _BIZINFO_RELOCATION_MARKERS)
    if any(marker in compact_summary for marker in _BIZINFO_UNRESTRICTED_MARKERS) and not has_relocation_condition:
        return ["전국"]

    restrictions = _bizinfo_local_restriction_regions(title, summary, agency)
    return restrictions or normalize_bizinfo_regions(hashtags)


def region_match_scope(
    user_region: str | None,
    policy_regions: list[str] | None,
) -> RegionMatchScope:
    if not user_region:
        return "unknown"
    regions = policy_regions or []
    if "전국" in regions:
        return "nationwide"
    user = resolve_region(user_region)
    if not user or not regions:
        return "unknown"

    policy_sidos = {resolved.sido for value in regions if (resolved := resolve_region(value)) is not None}
    if not policy_sidos:
        return "unknown"
    policy_equivalents = set().union(*(_equivalent_sidos(sido) for sido in policy_sidos))
    return "exact" if _equivalent_sidos(user.sido).intersection(policy_equivalents) else "mismatch"


def _haversine_km(origin: tuple[float, float], target: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, origin)
    lat2, lon2 = map(radians, target)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    haversine = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(haversine))


def region_distance_km(
    user_region: str | None,
    policy_regions: list[str] | None,
) -> float | None:
    origin = resolve_region(user_region)
    if not origin or not policy_regions or "전국" in policy_regions:
        return None

    distances: list[float] = []
    for value in policy_regions:
        target = resolve_region(value)
        if target:
            distances.append(
                _haversine_km(
                    (origin.latitude, origin.longitude),
                    (target.latitude, target.longitude),
                )
            )
    return round(min(distances), 1) if distances else None


def nearest_sidos(region: str | None) -> list[tuple[str, float]]:
    origin = resolve_region(region)
    if not origin:
        return []
    origin_equivalents = _equivalent_sidos(origin.sido)
    values = [
        (
            sido,
            round(
                _haversine_km(
                    (origin.latitude, origin.longitude),
                    SIDO_CENTERS[sido],
                ),
                1,
            ),
        )
        for sido in BIZINFO_REGION_TAGS
        if not _equivalent_sidos(sido).intersection(origin_equivalents)
    ]
    return sorted(values, key=lambda item: item[1])


def youth_codes(zip_codes: str | None) -> list[str]:
    return [code.strip() for code in (zip_codes or "").split(",") if code.strip()]


def youth_policy_is_nationwide(
    zip_codes: str | None,
    region_label: str | None = None,
) -> bool:
    if region_label == "전국":
        return True
    if region_label:
        return False
    prefixes = {
        sido
        for sido, prefix in SIDO_CODE_PREFIXES.items()
        if any(code.startswith(prefix) for code in youth_codes(zip_codes))
    }
    return len(prefixes) >= 15


def youth_policy_region_scope(
    user_region: str | None,
    zip_codes: str | None,
    region_label: str | None = None,
) -> RegionMatchScope:
    codes = youth_codes(zip_codes)
    raw_codes_are_nationwide = youth_policy_is_nationwide(zip_codes)

    if region_label == "전국":
        return "nationwide"
    if region_label and (raw_codes_are_nationwide or not codes):
        label_scope = region_match_scope(
            user_region,
            [part.strip() for part in region_label.split(",") if part.strip()],
        )
        if label_scope != "unknown":
            return label_scope
    if raw_codes_are_nationwide:
        return "nationwide"

    user = resolve_region(user_region)
    if not user:
        return "unknown"
    if not codes:
        return "unknown"

    if user.youth_code:
        code_prefix = user.youth_code[:4]
        return "exact" if any(code.startswith(code_prefix) for code in codes) else "mismatch"
    sido_prefix = SIDO_CODE_PREFIXES[user.sido]
    return "exact" if any(code.startswith(sido_prefix) for code in codes) else "mismatch"


def youth_region_label(zip_codes: str | None) -> str | None:
    codes = youth_codes(zip_codes)
    if not codes:
        return None
    if youth_policy_is_nationwide(zip_codes):
        return "전국"
    if len(codes) == 1 and (municipality := _MUNICIPALITY_BY_CODE.get(codes[0])):
        return municipality.name

    matched = [sido for sido, prefix in SIDO_CODE_PREFIXES.items() if any(code.startswith(prefix) for code in codes)]
    return ", ".join(matched) or zip_codes


def youth_local_authority_region_label(*organization_names: str | None) -> str | None:
    """등록·주관기관명에 명시된 지방자치단체의 시·도를 반환한다."""

    compact = _compact(" ".join(name for name in organization_names if name))
    if not compact:
        return None

    formal_hint = _formal_sido_hint(compact)
    if formal_hint:
        return formal_hint

    _, candidates = _best_contained_match(compact)
    municipality = _select_municipality(candidates, None)
    return municipality.sido if municipality else None
