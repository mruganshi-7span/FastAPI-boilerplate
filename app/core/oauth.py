from authlib.integrations.starlette_client import OAuth

from app.core.config import get_settings

settings = get_settings()

oauth = OAuth()

# OIDC discovery: Authlib fetches Google's endpoints and signing keys from the metadata URL, and
# verifies the id_token (signature, issuer, audience, nonce) during authorize_access_token.
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
