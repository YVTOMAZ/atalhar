from atalhar.fingerprint import fingerprint, normalize, sanitize_url


def test_sanitize_url_removes_query_and_creds():
    url = "https://user:pass@example.com/path?token=secret&x=1#frag"
    assert sanitize_url(url) == "https://example.com/path"


def test_sanitize_url_no_scheme_passthrough():
    assert sanitize_url("api.exemplo.test") == "api.exemplo.test"


def test_normalize_placeholders():
    assert normalize("buscar PR 12 em 2026-11-16 uuid 123e4567-e89b-12d3-a456-426614174000") == \
        "buscar PR {n} em {data} uuid {id}"


def test_same_task_different_ids_same_fingerprint():
    a = fingerprint("consultar", "https://api.exemplo.test/items/12", "GET /items/12")
    b = fingerprint("consultar", "https://api.exemplo.test/items/99", "GET /items/99")
    assert a == b


def test_different_tasks_different_fingerprint():
    a = fingerprint("consultar", "https://api.exemplo.test/items/12", "GET /items/12")
    b = fingerprint("consultar", "https://api.exemplo.test/users/12", "GET /users/12")
    assert a != b