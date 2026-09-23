# Authentication boundary

SSO implementation is deferred at the user's request. The temporary local preview
policy permits only explicitly enabled development mode with matching loopback
Origin and Host. Keep the development server bound to 127.0.0.1 and do not expose
it through a reverse proxy. Preview tokens grant all-department access.

Production fails closed. Before enabling production, require a verified server-side
SSO session and derive department RLS from trusted role claims. Never accept scope
or arbitrary dashboard UUIDs from browser input. Do not use the preview identity
for production authorization.
