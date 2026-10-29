import os
from urllib.parse import quote_plus

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://hybrid_superset:"
    + quote_plus(os.environ["SUPERSET_METADATA_PASSWORD"])
    + "@metadata:5432/hybrid_superset"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
FEATURE_FLAGS = {"EMBEDDED_SUPERSET": True, "ALERT_REPORTS": False}
# Embedding endpoints and dashboard-level origins will be configured with dashboards.
GUEST_TOKEN_JWT_SECRET = os.environ["SUPERSET_GUEST_TOKEN_SECRET"]
GUEST_TOKEN_JWT_EXP_SECONDS = 300
CACHE_CONFIG = {"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": "redis://redis:6379/0", "CACHE_KEY_PREFIX": "hybrid_general_", "CACHE_DEFAULT_TIMEOUT": 300}
FILTER_STATE_CACHE_CONFIG = {**CACHE_CONFIG, "CACHE_KEY_PREFIX": "hybrid_filter_", "CACHE_DEFAULT_TIMEOUT": 86400}
EXPLORE_FORM_DATA_CACHE_CONFIG = {**CACHE_CONFIG, "CACHE_KEY_PREFIX": "hybrid_explore_", "CACHE_DEFAULT_TIMEOUT": 86400}
# Query-result caching is disabled for the initial comparison baseline.
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
WTF_CSRF_ENABLED = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
