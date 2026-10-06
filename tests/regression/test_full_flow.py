"""One test walking the whole register -> login -> create-profile -> fetch
chain end to end, mirroring how a real client would actually use the API."""
from tests.conftest import login, register_user


async def test_provider_can_register_login_and_publish_a_profile(client):
    create_response = await register_user(
        client, "salon@example.com", password="secret123", role="provider", full_name="Salon Owner"
    )
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]

    token = await login(client, "salon@example.com", "secret123")

    profile_response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Salon Co",
            "bio": "Full service salon",
            "years_experience": 5,
            "categories": ["hair", "nails"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile_response.status_code == 201
    profile = profile_response.json()
    assert profile["user_id"] == user_id

    fetched = await client.get(f"/v1/providers/{profile['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == profile
