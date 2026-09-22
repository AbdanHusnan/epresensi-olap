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
# No guest access is granted until SSO scopes and embedded dashboards are configured.
GUEST_ROLE_NAME = 'DashboardGuest'
