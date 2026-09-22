# SSO integration boundary

Pending: provider/protocol, session verification, actual roles and department scopes.
Current routes render only an empty shell and do not read protected data.
Before adding an embedded dashboard or guest-token endpoint, require a verified
server-side session and derive permitted department IDs from trusted claims.
Do not add a mock identity or an unrestricted guest-token fallback.
