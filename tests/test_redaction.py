from app.security import redact_obj, redact_text


def test_redacts_email():
    assert "[REDACTED_EMAIL]" in redact_text("contact me at john.doe@example.com")


def test_redacts_bearer_token():
    out = redact_text("Authorization: Bearer abc.def.ghi123")
    assert "abc.def.ghi123" not in out
    assert "Bearer [REDACTED]" in out


def test_redacts_signed_url():
    out = redact_text(
        "see https://bucket.s3.amazonaws.com/key?X-Amz-Signature=deadbeef"
    )
    assert "[REDACTED_URL]" in out
    assert "amazonaws" not in out


def test_redacts_api_token_shape():
    out = redact_text("key is sk_live_0123456789abcdef")
    assert "[REDACTED_TOKEN]" in out
    assert "sk_live_0123456789abcdef" not in out


def test_redacts_jwt():
    jwt = "eyJhbGciOi.eyJzdWIiOi.s3cr3tSignature"
    out = redact_text(f"token={jwt}")
    assert "[REDACTED_JWT]" in out


def test_redact_obj_drops_sensitive_keys_and_scrubs_values():
    payload = {
        "token": "should-vanish",
        "note": "ping admin@corp.com now",
        "nested": {"password": "p", "url": "https://x.test/a?b=c"},
        "list": ["plain", "Bearer xyz123"],
    }
    out = redact_obj(payload)
    assert out["token"] == "[REDACTED]"
    assert "[REDACTED_EMAIL]" in out["note"]
    assert out["nested"]["password"] == "[REDACTED]"
    assert "[REDACTED_URL]" in out["nested"]["url"]
    assert out["list"][0] == "plain"
    assert "Bearer [REDACTED]" in out["list"][1]


def test_redact_passthrough_for_clean_text():
    assert redact_text("Instagram reel draft") == "Instagram reel draft"
    assert redact_text(None) is None
