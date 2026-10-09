"""
Confirms add_security_headers (app/main.py) is actually wired in, not
just declared — checks real response headers from a running request,
same reasoning as tests/regression/test_response_compression.py for
GZipMiddleware.
"""


async def test_response_includes_baseline_security_headers(client):
    response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


async def test_security_headers_present_even_on_error_responses(client):
    response = await client.get("/v1/providers/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
