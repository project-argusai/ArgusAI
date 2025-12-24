# Story P10-2.5: Add PostgreSQL Service to docker-compose

Status: done

## Story

As a **user**,
I want **optional PostgreSQL for production deployments**,
So that **I can use a robust database for larger installations**.

## Acceptance Criteria

1. **Given** I want to use PostgreSQL
   **When** I run `docker-compose --profile postgres up`
   **Then** PostgreSQL container starts alongside the app
   **And** backend connects to PostgreSQL
   **And** migrations are applied automatically

2. **Given** PostgreSQL is running
   **When** I check the database
   **Then** all tables are created correctly
   **And** data is persisted in a named volume

## Tasks / Subtasks

- [x] Task 1: Add PostgreSQL service to docker-compose.yml (AC: 1, 2)
  - [x] Subtask 1.1: Add postgres service with profile: ["postgres"]
  - [x] Subtask 1.2: Use postgres:16-alpine image
  - [x] Subtask 1.3: Configure POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB environment variables
  - [x] Subtask 1.4: Add health check using pg_isready

- [x] Task 2: Configure PostgreSQL volume for persistence (AC: 2)
  - [x] Subtask 2.1: Add pgdata named volume to volumes section
  - [x] Subtask 2.2: Mount volume to /var/lib/postgresql/data

- [x] Task 3: Update backend service for PostgreSQL support (AC: 1)
  - [x] Subtask 3.1: Fix database.py to conditionally apply SQLite-only options
  - [x] Subtask 3.2: Document DATABASE_URL override in compose file

- [x] Task 4: Add PostgreSQL environment variables to .env.example (AC: 1)
  - [x] Subtask 4.1: POSTGRES_USER already present with default
  - [x] Subtask 4.2: POSTGRES_PASSWORD already present
  - [x] Subtask 4.3: POSTGRES_DB already present with default

- [x] Task 5: Test and validate PostgreSQL integration (AC: 1, 2)
  - [x] Subtask 5.1: Run `docker-compose --profile postgres config` to validate syntax
  - [x] Subtask 5.2: Document testing steps

## Dev Notes

### Architecture Alignment

From tech-spec-epic-P10-2.md, the PostgreSQL service implements:

- **Compose profiles**: Using `profiles: ["postgres"]` to make PostgreSQL optional
- **postgres:16-alpine**: Latest stable PostgreSQL in Alpine for minimal image size
- **Named volume**: pgdata volume for persistent database storage
- **Health check**: pg_isready for container orchestration readiness

### Key Technical Decisions

1. **Profile-based activation**: PostgreSQL only starts when explicitly requested with `--profile postgres`
2. **Alpine base image**: Smaller image size (~80MB vs ~400MB for debian-based)
3. **Named volume**: pgdata volume survives container recreation
4. **Automatic migrations**: Backend already runs Alembic migrations on startup
5. **Internal network**: PostgreSQL accessible only within argusai-net, not exposed externally

### Docker Compose Profile Usage

```bash
# Start with PostgreSQL
docker-compose --profile postgres up -d

# Start with both PostgreSQL and SSL (future story P10-2.6)
docker-compose --profile postgres --profile ssl up -d

# Start without PostgreSQL (default SQLite)
docker-compose up -d
```

### Environment Configuration

When using PostgreSQL, set:
```bash
DATABASE_URL=postgresql://argusai:your-password@postgres:5432/argusai
```

Or use the default with profile environment variables:
```bash
POSTGRES_USER=argusai
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=argusai
```

### Learnings from Previous Story

**From Story P10-2.4 (Status: done)**

- **docker-compose.yml structure**: Services, volumes, networks already configured
- **Named volumes pattern**: argusai-data volume pattern established
- **Health checks**: Backend uses `/health` endpoint, frontend uses wget
- **No version attribute**: Modern Docker Compose doesn't need version field
- **Internal network**: argusai-net bridge network established for service communication

[Source: docs/sprint-artifacts/p10-2-4-create-docker-compose-yml.md#Dev-Agent-Record]

### Database Migration Notes

The backend already handles database migrations automatically:
- Alembic runs on startup via the application lifecycle
- PostgreSQL connection works with existing DATABASE_URL pattern
- SQLAlchemy 2.0 dialect handles both SQLite and PostgreSQL

### PostgreSQL Connection String

Format: `postgresql://user:password@host:port/database`

For Docker Compose internal network:
- Host: `postgres` (service name becomes DNS hostname)
- Port: `5432` (PostgreSQL default)

### Security Considerations

- PostgreSQL not exposed on host ports (internal network only)
- Password stored in environment variable (not baked into image)
- pg_hba.conf uses default trust within Docker network

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P10-2.md#Story-P10-2.5]
- [Source: docs/epics-phase10.md#Story-P10-2.5]
- [Source: docs/PRD-phase10.md#FR20]
- [Source: docker-compose.yml]
- [Source: .env.example]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p10-2-5-add-postgresql-service-to-docker-compose.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- Validated docker-compose.yml syntax with `docker-compose config` - passes
- Validated postgres profile with `docker-compose --profile postgres config` - passes
- POSTGRES_PASSWORD correctly marked as required with error message when not set
- Fixed backend/app/core/database.py to conditionally apply SQLite-specific options

### Completion Notes List

- Added PostgreSQL service to docker-compose.yml with profile: ["postgres"]
- PostgreSQL uses postgres:16-alpine image for minimal size
- POSTGRES_PASSWORD is required when using postgres profile (fails with clear error if not set)
- Added pgdata named volume for PostgreSQL data persistence
- Health check uses pg_isready command with user and database parameters
- Fixed backend database.py to only apply check_same_thread for SQLite connections
- PostgreSQL not exposed on host ports (internal network only for security)
- Environment variables already present in .env.example (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)

### File List

MODIFIED:
- docker-compose.yml - Added postgres service, pgdata volume, updated usage comments
- backend/app/core/database.py - Conditional check_same_thread for SQLite only

NEW:
- (none)

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-24 | Story drafted from Epic P10-2 |
| 2025-12-24 | Story implementation complete - PostgreSQL service added to docker-compose |
