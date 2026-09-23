import os
from urllib.parse import quote_plus

SECRET_KEY = os.environ['SUPERSET_SECRET_KEY']
SQLALCHEMY_DATABASE_URI = (
    'postgresql+psycopg2://superset:'
    + quote_plus(os.environ['SUPERSET_METADATA_PASSWORD'])
    + '@superset-db:5432/superset'
)
FEATURE_FLAGS = {'EMBEDDED_SUPERSET': True}
WTF_CSRF_ENABLED = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SQLLAB_TIMEOUT = 60
SQL_MAX_ROW = 10000
# Local embedding only; Next.js production guest-token access remains disabled.
GUEST_ROLE_NAME = 'DashboardGuest'

# Derive a dedicated signing key rather than using Superset's default guest secret.
import hashlib
import hmac
from superset.config import TALISMAN_CONFIG as DEFAULT_TALISMAN_CONFIG

GUEST_TOKEN_JWT_SECRET = hmac.new(
    SECRET_KEY.encode(), b"epresensi-embedded-guest-v1", hashlib.sha256
).hexdigest()
GUEST_TOKEN_JWT_EXP_SECONDS = 300

# Browser framing is limited to the Next.js development origin and Superset itself.
TALISMAN_CONFIG = {
    **DEFAULT_TALISMAN_CONFIG,
    "frame_options": None,
    "content_security_policy": {
        **DEFAULT_TALISMAN_CONFIG["content_security_policy"],
        "frame-ancestors": ["'self'", "http://127.0.0.1:3002"],
    },
}
