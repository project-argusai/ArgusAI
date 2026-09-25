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
| `/ws` and `/ws/*` | WebSocket upgrade handlers authenticate the session before `accept`. HTTP middleware does not run on these upgrades. |
| `/api/v1/cameras/{camera_id}/stream` | Camera WebSocket upgrade handler authenticates before `accept`. The suffix match is the path segment `/stream` only. |
Thumbnail and event-frame routes are not in `EXCLUDED_PATHS`. `AuthMiddleware`
authenticates them. Route-level authorization must never assume that the
middleware enforced access on an excluded path.

These HTTP camera paths do **not** end in the `/stream` segment, so
`AuthMiddleware` authenticates them (JWT/cookie or an API key with
`read:cameras`):

- `GET /api/v1/cameras/stream/metrics`
- `GET /api/v1/cameras/{camera_id}/stream/info`
- `GET /api/v1/cameras/{camera_id}/stream/snapshot`

`GET /api/v1/system/ai-processing-stream` and
`GET /api/v1/system/ai-processing-hot-stream` end in the letters `stream` but
not the `/stream` segment, so they stay on `AuthMiddleware` plus
`get_current_user`. There is no HTTP MJPEG or HLS camera route. HomeKit video
uses the HAP accessory server, not these HTTP paths.
