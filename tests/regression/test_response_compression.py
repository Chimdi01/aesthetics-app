"""
Confirms GZipMiddleware (app/main.py) is actually wired in and compressing
responses over its size threshold, not just declared — httpx negotiates
and transparently decompresses gzip by default, so a response with
Content-Encoding: gzip in its headers is direct evidence the middleware
ran, not an assumption.
"""


async def test_large_json_response_is_gzip_compressed(client):
    # /openapi.json is comfortably over GZipMiddleware's minimum_size (500
    # bytes) for any app with more than a couple of endpoints, and needs
    # no auth or test data setup.
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


async def test_tiny_response_is_not_compressed(client):
    # Below GZipMiddleware's minimum_size — compressing it would add
    # overhead for no benefit, so it's correctly left alone.
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("content-encoding") != "gzip"
