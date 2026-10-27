import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_biometric_auth_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Challenge generation
        res = await client.get("/api/v1/auth/biometric/challenge")
        assert res.status_code == 200
        challenge = res.json()["challenge"]
        assert len(challenge) > 20

        # 2. Status check
        res = await client.get("/api/v1/auth/biometric/status")
        assert res.status_code == 200
        data = res.json()
        assert "has_registered_credentials" in data

        # 3. Registration without password or token should fail
        res = await client.post("/api/v1/auth/biometric/register", json={
            "credential_id": "test_cred_12345",
            "device_name": "Test Mac Touch ID"
        })
        assert res.status_code == 401

        # 4. Registration with valid password should succeed
        res = await client.post("/api/v1/auth/biometric/register", json={
            "credential_id": "test_cred_12345",
            "device_name": "Test Mac Touch ID",
            "password": "mwps@1534"
        })
        assert res.status_code == 200
        reg_data = res.json()
        assert reg_data["authenticated"] is True
        token = reg_data["token"]
        assert token is not None

        # 5. Verify biometric authentication
        res = await client.post("/api/v1/auth/biometric/verify", json={
            "credential_id": "test_cred_12345",
            "challenge": challenge
        })
        assert res.status_code == 200
        auth_data = res.json()
        assert auth_data["authenticated"] is True
        assert auth_data["token"] is not None

        # 6. Verify with unrecognized credential should fail
        res = await client.post("/api/v1/auth/biometric/verify", json={
            "credential_id": "unknown_cred_999",
            "challenge": challenge
        })
        assert res.status_code == 401
