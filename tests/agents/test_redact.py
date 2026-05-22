import json

from src.agents.llm.redact import redact


def test_strips_common_secrets():
    text = ("api_key=sk-abcdefabcdefabcdef1234 "
            "password: hunter2supersecret "
            "Authorization: Bearer abcd1234efgh5678ijkl")
    out, n = redact(text)
    assert "sk-abcdefabcdefabcdef1234" not in out
    assert "hunter2supersecret" not in out
    assert "abcd1234efgh5678ijkl" not in out
    assert "[REDACTED" in out
    assert n >= 3


def test_strips_jwt_and_private_key():
    jwt = "eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM"
    out, _ = redact("session " + jwt)
    assert jwt not in out

    pk = "-----BEGIN RSA PRIVATE KEY-----\nMIIsecretkeymaterial\n-----END RSA PRIVATE KEY-----"
    out2, _ = redact(pk)
    assert "MIIsecretkeymaterial" not in out2


def test_truncates_oversized_content():
    out, _ = redact("x" * 5000)
    assert len(out) <= 4000 + 20


def test_real_shape_evidence_fixture():
    # Mirrors a web.exposed_sensitive_paths finding with a planted secret in the body.
    finding = {
        "title": "Sensitive resource reachable",
        "evidence": {"exposed": [{
            "path": "/ftp/acquisitions.md",
            "snippet": "This document is confidential! Do not distribute! token=sk-deadbeefdeadbeef0000",
        }]},
    }
    out, n = redact(json.dumps(finding))
    assert "sk-deadbeefdeadbeef0000" not in out   # planted secret stripped
    assert n >= 1
    # Documented policy: for local owned lab targets, truncated body snippets
    # (our own test data) are allowed through after secret-stripping.
    assert "confidential" in out.lower()
