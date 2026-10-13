"""
GET /v1/specialties/ — public reference data, no auth needed.
"""


async def test_list_specialties_requires_no_token(client):
    response = await client.get("/v1/specialties/")
    assert response.status_code == 200


async def test_list_specialties_returns_slug_and_categories_only(client):
    response = await client.get("/v1/specialties/")
    body = response.json()
    assert len(body) > 0
    for entry in body:
        assert set(entry.keys()) == {"slug", "categories"}


async def test_texture_specialty_belongs_to_hair_and_barber(client):
    response = await client.get("/v1/specialties/")
    by_slug = {entry["slug"]: entry["categories"] for entry in response.json()}
    assert set(by_slug["coily"]) == {"hair", "barber"}


async def test_fade_belongs_to_barber_only(client):
    response = await client.get("/v1/specialties/")
    by_slug = {entry["slug"]: entry["categories"] for entry in response.json()}
    assert by_slug["fade"] == ["barber"]
