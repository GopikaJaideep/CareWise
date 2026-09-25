"""Sign-up checks: real email domains, one account per inbox, and email confirmation."""
import httpx
import pytest
from email_validator import EmailUndeliverableError
from fastapi import Depends, FastAPI
from jose import jwt

from app.api import auth_routes
from app.core.auth import create_access_token, create_email_verification_token
from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import User

SIGNUP = {"password": "a-long-password", "display_name": "Sam"}


@pytest.fixture
async def client(db, monkeypatch):
    sent = []

    async def capture(to, link):
        sent.append((to, link))
        return True

    monkeypatch.setattr(auth_routes, "send_verification_email", capture)
    app = FastAPI()
    app.include_router(auth_routes.router)

    async def session():
        yield db

    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.sent = sent
        yield c


async def settle():
    """Let the background confirmation-email task run."""
    import asyncio
    for _ in range(3):
        await asyncio.sleep(0)


def token_from(link: str) -> str:
    return link.split("token=", 1)[1]


# --- Real email domains -------------------------------------------------------------------------------

async def test_made_up_email_domains_are_rejected(client, monkeypatch):
    def fake_dns(email, check_deliverability):
        if "madeup" in email:
            raise EmailUndeliverableError("The domain name madeup-domain.xyz does not exist.")
        return type("R", (), {"normalized": email})()

    monkeypatch.setattr(get_settings(), "email_check_deliverability", True)
    monkeypatch.setattr(auth_routes, "validate_email", fake_dns)
    r = await client.post("/api/auth/register", json={**SIGNUP, "email": "someone@madeup-domain.xyz"})
    assert r.status_code == 400 and "check it for typos" in r.json()["detail"]
    ok = await client.post("/api/auth/register", json={**SIGNUP, "email": "someone@realmail.com"})
    assert ok.status_code == 201


# --- One account per inbox ----------------------------------------------------------------------------

async def test_email_case_doesnt_create_a_second_account(client):
    first = await client.post("/api/auth/register", json={**SIGNUP, "email": "Sam.Carer@Gmail.com"})
    assert first.status_code == 201
    again = await client.post("/api/auth/register", json={**SIGNUP, "email": "sam.carer@gmail.com"})
    assert again.status_code == 400 and again.json()["detail"] == "Email already registered"


async def test_login_ignores_email_case(client):
    await client.post("/api/auth/register", json={**SIGNUP, "email": "sam@realmail.com"})
    r = await client.post("/api/auth/login", json={"email": "SAM@RealMail.com", "password": SIGNUP["password"]})
    assert r.status_code == 200


# --- Email confirmation ---------------------------------------------------------------------------------

async def test_signup_sends_a_confirmation_link_that_verifies_the_address(client, db):
    r = await client.post("/api/auth/register", json={**SIGNUP, "email": "sam@realmail.com"})
    await settle()
    (to, link), = client.sent
    assert to == "sam@realmail.com" and "/verify-email?token=" in link
    user = await db.get(User, r.json()["user_id"])
    assert user.email_verified is False

    confirmed = await client.post("/api/auth/verify-email", json={"token": token_from(link)})
    assert confirmed.status_code == 200 and confirmed.json()["email_verified"] is True
    await db.refresh(user)
    assert user.email_verified is True


async def test_bad_or_mismatched_confirmation_links_are_refused(client, db):
    assert (await client.post("/api/auth/verify-email", json={"token": "nonsense"})).status_code == 400
    # A link issued for an address the account no longer has doesn't confirm the new one.
    stale = create_email_verification_token(1, "old-address@realmail.com")
    assert (await client.post("/api/auth/verify-email", json={"token": stale})).status_code == 400


async def test_a_login_token_cannot_confirm_an_email(client):
    assert (await client.post("/api/auth/verify-email", json={"token": create_access_token(1)})).status_code == 400


# --- Tokens have one purpose each -------------------------------------------------------------------------

async def test_a_confirmation_link_cannot_be_used_to_log_in(client, db):
    from app.core.auth import get_current_user

    app = FastAPI()

    @app.get("/who")
    async def who(user: User = Depends(get_current_user)):
        return {"id": user.id}

    async def session():
        yield db

    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        confirm = create_email_verification_token(1, "a@example.com")
        assert (await c.get("/who", headers={"Authorization": f"Bearer {confirm}"})).status_code == 401
        assert (await c.get("/who", headers={"Authorization": f"Bearer {create_access_token(1)}"})).json() == {"id": 1}
        # Tokens issued before tokens had a purpose still work: nobody is signed out.
        s = get_settings()
        legacy = jwt.encode({"sub": "1", "exp": 4102444800}, s.secret_key, algorithm=s.algorithm)
        assert (await c.get("/who", headers={"Authorization": f"Bearer {legacy}"})).status_code == 200


async def test_resend_needs_login_and_only_sends_when_unconfirmed(client, db):
    assert (await client.post("/api/auth/resend-verification")).status_code == 401
    r = await client.post("/api/auth/register", json={**SIGNUP, "email": "sam@realmail.com"})
    await settle()
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/api/auth/resend-verification", headers=auth)).status_code == 202
    await settle()
    assert len(client.sent) == 2
    user = await db.get(User, r.json()["user_id"])
    user.email_verified = True
    await db.commit()
    await client.post("/api/auth/resend-verification", headers=auth)
    await settle()
    assert len(client.sent) == 2  # already confirmed: nothing sent


# --- Where data lives ------------------------------------------------------------------------------------

async def test_health_says_whether_data_survives_a_redeploy():
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        body = (await c.get("/health")).json()
    assert body["status"] == "healthy"
    assert body["database"] in ("sqlite", "postgres") and body["persistent"] == (body["database"] == "postgres")
