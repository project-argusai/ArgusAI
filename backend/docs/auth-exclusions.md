# HTTP authentication exclusions

`AuthMiddleware` only skips access-token authentication for these paths. A
caller-provided header or `TESTING` environment variable cannot disable it.
Ordinary CORS `OPTIONS` preflight requests are also exempt; browsers do not send
credentials on those requests and no application handler should mutate state.

| Path | Reason for public access or separate authentication |
| --- | --- |
| `/`, `/health` | API landing and liveness responses. |
| `/metrics` | Prometheus scraping; deployment must limit network access to this endpoint. |
| `/docs`, `/redoc`, `/openapi.json` | API documentation and schema. |
| `/api/v1/auth/login` | Accepts credentials and issues a session. |
| `/api/v1/auth/logout` | Clears an existing cookie and optionally revokes a supplied refresh token. |
| `/api/v1/auth/refresh` | Validates and rotates a refresh token. |
| `/api/v1/auth/setup-status` | Lets the login UI detect initial setup. |
| `/api/v1/mobile/auth/pair` | Starts the pairing-code flow. |
| `/api/v1/mobile/auth/status/{code}` | Polls by a short-lived pairing code. |
| `/api/v1/mobile/auth/exchange` | Exchanges a confirmed pairing code for tokens. |
| `/api/v1/mobile/auth/refresh` | Validates and rotates a mobile refresh token. |
| `/ws` and `/ws/*` | WebSocket upgrade handlers must authenticate their own sessions; HTTP middleware does not secure WebSocket scopes. |
| `/api/v1/cameras/{camera_id}/stream` | WebSocket upgrade handler owns authentication. |
| `/api/v1/thumbnails/*` | Existing image-tag access path. It exposes camera media and needs the separate media authorization remediation. |
| `/api/v1/events/{event_id}/frames*` | Existing image-tag access path. It exposes event media and needs the separate media authorization remediation. |

The final two media exclusions are known security gaps tracked separately from
the User-Agent bypass. Route-level authorization must never assume that the
middleware enforced access on an excluded path.
