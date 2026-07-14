from app.core.privacy import (
    detect_sensitive_data,
    privacy_guard_reply,
    redact_sensitive_structure,
    redact_sensitive_text,
)


def test_detects_and_redacts_supported_sensitive_identifiers():
    content = (
        "주민번호 991332-1234567, 휴대전화 010-1234-5678, 이메일 person@example.com, "
        "계좌번호 123-456-789012, 카드 1234-5678-9012-3456"
    )

    detected = detect_sensitive_data(content)
    redacted = redact_sensitive_text(content)

    assert detected == [
        "주민등록번호·외국인등록번호 형태",
        "전화번호 형태",
        "이메일 주소",
        "계좌번호 형태",
        "카드·금융번호 형태",
    ]
    assert "991332-1234567" not in redacted
    assert "010-1234-5678" not in redacted
    assert "person@example.com" not in redacted
    assert "123-456-789012" not in redacted
    assert "1234-5678-9012-3456" not in redacted
    assert "[민감정보 삭제]" in redacted


def test_privacy_detection_does_not_block_normal_policy_conditions():
    content = "서울에 사는 만 24세이고 최대 5천만원 금융지원을 찾고 있어"

    assert detect_sensitive_data(content) == []
    assert redact_sensitive_text(content) == content


def test_nested_memory_and_guard_reply_never_repeat_sensitive_value():
    sensitive = "991332-1234567"
    value = {
        "profile": {"memo": sensitive},
        "pending_request": {"original_request": f"내 번호는 {sensitive}"},
    }

    redacted = redact_sensitive_structure(value)
    reply = privacy_guard_reply(detect_sensitive_data(sensitive))

    assert sensitive not in str(redacted)
    assert sensitive not in reply
    assert "정책 검색을 중단" in reply
    assert "답변 생성 모델이나 외부 정책 API에 전달하지 않고" in reply
