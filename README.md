# Nexora RealtyOS Backend

Django REST backend for a multi-tenant real-estate agency operating system. It supports the complete workflow from public discovery and lead capture through negotiation, documents, closing, rentals, reporting, and subscription billing.

## Capabilities

- Agency registration, activation, branding, and subscription enforcement
- Owner, manager, agent, and super-admin roles
- JWT authentication with email OTP verification, password recovery, refresh rotation, and token blacklisting
- Property CRUD, assignment, publication, filtering, and media
- Public agency, agent, listing, inquiry, and site-visit APIs
- Phone normalization and duplicate public-lead reuse
- Lead pipeline, property interests, interaction history, and status audit trail
- Due/overdue follow-ups and idempotent reminders
- Site-visit scheduling, outcomes, cancellations, and reminders
- Property view/contact conversion events and dashboard summaries
- Meta account connection plus Facebook and Instagram image publishing/scheduling
- OpenAPI, Swagger UI, ReDoc, health checks, and request throttling
- Contacts and owners; deals, offers, token amounts, commissions, and closing
- Documents linked to properties, clients, owners, and deals
- Rental leases, deposits, rent dates, renewals, tasks, and reminders
- Notifications, invitations, role/access management, and audit logs
- Smart property matching, comparison, advanced reports, and agent performance
- Custom fields and configurable lead/deal pipeline stages
- Customer accounts, favorites, saved-search alerts, and appointment booking
- Public map search, canonical share URLs, SEO metadata, and video tours
- Stripe Checkout, signed webhooks, billing portal, and payment history
- Super-admin metrics and agency activation/suspension controls

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

The container waits for PostgreSQL, applies migrations, collects static files, and starts Gunicorn as an unprivileged user. PostgreSQL, media, and static data use persistent Docker volumes.

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

# Create task and lease-renewal notifications
python manage.py send_task_reminders

# Email customers about new saved-search matches
python manage.py send_saved_search_alerts
```

Docker Compose includes a scheduler service that runs these jobs every five minutes. On other platforms, configure the same commands in the platform scheduler.

## Production requirements

- Set `DEBUG=False`.
- Set a strong `DJANGO_SECRET_KEY`; startup fails without one in production.
- Set exact `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`.
- Configure SMTP and persistent/object media storage.
- Configure `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the three `STRIPE_PRICE_*` IDs. Point Stripe webhooks to `/api/webhooks/stripe/`.
- Enable HTTPS redirect and secure cookies behind a trusted reverse proxy.
- Back up PostgreSQL and monitor `/api/health/`.
- Run reminder and publishing commands from a scheduler.
- Set `PUBLIC_API_BASE_URL` to the public HTTPS API origin for Instagram image fetching.
- Keep the debug payment endpoint unavailable; it is excluded when `DEBUG=False`.

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) for the frontend-facing API contract.
