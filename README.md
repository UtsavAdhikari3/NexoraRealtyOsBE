# Nexora RealtyOS Backend

Django REST backend for a multi-tenant real-estate agency operating system. The MVP supports agency websites powered by public APIs, property inventory, buyer CRM, agent assignment, follow-ups, site visits, analytics, and Meta/Facebook publishing.

## MVP capabilities

- Agency registration, activation, branding, and subscription enforcement
- Owner, manager, agent, and super-admin roles
- JWT authentication with email OTP verification
- Property CRUD, assignment, publication, filtering, and media
- Public agency, agent, listing, inquiry, and site-visit APIs
- Phone normalization and duplicate public-lead reuse
- Lead pipeline, property interests, interaction history, and status audit trail
- Due/overdue follow-ups and idempotent reminders
- Site-visit scheduling, outcomes, cancellations, and reminders
- Property view/contact conversion events and dashboard summaries
- Meta account connection and Facebook post publishing/scheduling
- OpenAPI, Swagger UI, ReDoc, health checks, and request throttling

## Local development

1. Copy `.env.example` to `.env` and fill in secrets as needed.
2. Start the stack:

   ```bash
   docker compose up --build
   ```

3. Open:

   - API: `http://localhost:8000/api/`
   - Swagger: `http://localhost:8000/api/docs/`
   - ReDoc: `http://localhost:8000/api/redoc/`
   - Health: `http://localhost:8000/api/health/`

The container waits for PostgreSQL, applies migrations, and starts Gunicorn.

## Validation

Run checks and tests inside Docker:

```bash
docker compose exec -T api python manage.py check
docker compose exec -T api python manage.py makemigrations --check --dry-run
docker compose exec -T api python manage.py test
```

Generate the OpenAPI schema:

```bash
docker compose exec -T api python manage.py spectacular --file /tmp/schema.yml --validate
```

## Scheduled commands

Run these commands from cron or a platform scheduler. They are idempotent and safe to invoke repeatedly.

```bash
# Send lead and site-visit reminders due within 24 hours
python manage.py send_due_reminders --hours 24

# Publish social posts whose scheduled time has arrived
python manage.py publish_scheduled_posts
```

For an MVP deployment, run each command every 5–10 minutes.

## Production requirements

- Set `DEBUG=False`.
- Set a strong `DJANGO_SECRET_KEY`; startup fails without one in production.
- Set exact `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`.
- Configure SMTP and persistent/object media storage.
- Enable HTTPS redirect and secure cookies behind a trusted reverse proxy.
- Back up PostgreSQL and monitor `/api/health/`.
- Run reminder and publishing commands from a scheduler.
- Keep the debug payment endpoint unavailable; it is excluded when `DEBUG=False`.

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) for the frontend-facing API contract.
