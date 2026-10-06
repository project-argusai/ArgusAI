"""Read-only MCP connector for assistant bots (issue #648).

Not related to ``app.services.mcp_context`` (AI prompt context). This package
exposes a small set of read-only tools over the Model Context Protocol so an
assistant can answer questions such as "anything happen at home in the last
hour?" from stored event descriptions.

Modules:
- ``time_window``: parse ``since``/``window`` values and format local times
- ``queries``: ORM-only read queries that build compact tool results
- ``thumbnails``: short-lived HMAC-signed thumbnail URLs
- ``audit``: audit-log rows for every tool call
- ``server``: MCP tool definitions and dispatch
"""
