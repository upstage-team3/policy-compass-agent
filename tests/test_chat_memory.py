from app.repositories.chat_memory import _safe_content


def test_safe_content_masks_sensitive_identifiers_and_limits_length():
    content = "주민번호 900101-1234567 카드 1234-5678-9012-3456 " + ("가" * 5000)

    sanitized = _safe_content(content)

    assert "900101-1234567" not in sanitized
    assert "1234-5678-9012-3456" not in sanitized
    assert "[민감정보 삭제]" in sanitized
    assert len(sanitized) <= 4000
