"""Default-deny route policy for machine API keys.

Only documented event and camera API families are available to API keys.
User sessions are authorized separately by role dependencies.
"""


def required_api_key_scope(method: str, path: str, prefix: str = "/api/v1") -> str | None:
    """Return the scope needed for an allowed route, or None to deny the key."""
    method = method.upper()
    api_prefix = prefix.rstrip("/")
    events = f"{api_prefix}/events"
    cameras = f"{api_prefix}/cameras"

    if path == events or path.startswith(f"{events}/"):
        if method == "GET":
            return "read:events"
        # No write:events scope exists. Deliberately require a privileged key
        # for create, feedback, reanalysis, and all event deletion paths.
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            return "admin"
        return None

    if path == cameras or path.startswith(f"{cameras}/"):
        if method == "GET":
            return "read:cameras"
        if method == "POST" and path == cameras:
            return "write:cameras"

        remainder = path[len(cameras) + 1:]
        segments = remainder.split("/")
        if len(segments) == 1 and segments[0]:
            if method in {"PUT", "DELETE"}:
                return "write:cameras"
        if len(segments) == 2 and segments[0]:
            if method == "POST" and segments[1] in {
                "reconnect", "enable-capture", "disable-capture"
            }:
                return "write:cameras"
            if method == "PUT" and segments[1] in {"zones", "schedule"}:
                return "write:cameras"
            if method == "PATCH" and segments[1] == "audio":
                return "write:cameras"
        if (len(segments) == 3 and segments[0]
                and segments[1:] == ["motion", "config"] and method == "PUT"):
            return "write:cameras"

    return None


def api_key_allows(scopes: list[str], required_scope: str | None) -> bool:
    """Admin keys may use allowlisted routes, but never bypass the allowlist."""
    return required_scope is not None and (
        "admin" in scopes or required_scope in scopes
    )
