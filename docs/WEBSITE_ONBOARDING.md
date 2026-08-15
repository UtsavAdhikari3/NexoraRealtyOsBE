# Agency website onboarding and publishing

## Product flow

1. Registration creates an agency slug and an unpublished website draft.
2. Payment and email verification finish before normal authenticated use.
3. Owners and managers with incomplete onboarding are routed to `/onboarding/website`.
4. The nine-step creator saves only `website_draft_config`.
5. A signed, 24-hour preview URL renders the draft with `noindex, nofollow`.
6. Publish validates the required checklist, snapshots the normalized draft into `website_published_config`, increments `website_config_version`, and makes the slug public.
7. Later edits remain private until the next publish. Unpublish removes the tenant from public API queries without deleting either configuration.

Agents cannot read, edit, upload, publish, or unpublish website configuration. The CRM also hides and route-protects these controls.

## One normalized configuration

`agencies.website_onboarding.DEFAULT_WEBSITE_CONFIG` is the authoritative schema for branding, content, contact details, social links, navigation, enabled pages, homepage sections, SEO, localization, calls to action, featured-property behavior, and media references.

Unknown keys are rejected. Nested collections have strict item fields and limits. URLs are restricted to HTTP/HTTPS (or safe internal paths where supported), emails and phone numbers are validated, colours must be six-digit hex values, fonts come from an allow-list, and navigation/page/section references must use supported identifiers.

Legacy top-level agency fields are normalized into the draft for compatibility. The publish snapshot is also mirrored to the old `website_config` field during rollout, but public serializers read the published snapshot and never read the draft.

## Configuration lifecycle

```text
CRM field
  -> PATCH /api/agencies/me/website-onboarding/
  -> normalized website_draft_config
  -> signed preview API (draft only)
  -> POST /api/agencies/me/website/publish/
  -> website_published_config + version increment
  -> public agency API (published only)
  -> AgencySiteProvider + CSS variables
  -> tenant storefront components
```

The storefront requests agency configuration with `cache: no-store`, so a successful publish is visible immediately. Property-list caches are separate from website configuration.

## API surface

- `GET/PATCH /api/agencies/me/website-onboarding/`
- `POST/DELETE /api/agencies/me/website-onboarding/media/`
- `POST /api/agencies/me/website-onboarding/validate/`
- `POST /api/agencies/me/website-onboarding/complete/`
- `GET /api/agencies/me/website/preview/`
- `POST /api/agencies/me/website/publish/`
- `POST /api/agencies/me/website/unpublish/`

The readiness response contains `is_ready_to_publish`, `completion_percentage`, `missing_fields`, and individual checks.

## Media handling

Supported media include the primary, light, and dark logos; favicon; hero, about, property-placeholder, and social-sharing images; and multiple partner logos.

Uploads are checked for an allowed MIME type, a real decodable image, a 5 MB size limit, supported dimensions, a tenant-owned storage path, and a server-generated filename. Replacement and deletion preserve files referenced by the live snapshot and reject paths not owned by the tenant.

Public media URLs are built from `PUBLIC_API_BASE_URL`. Production must set this to the browser-reachable API origin, for example:

```text
PUBLIC_API_BASE_URL=https://api.nexorarealtyos.com
STOREFRONT_PUBLIC_URL=https://template.nexorarealtyos.com
```

The reverse proxy or object store must serve `/media/` from persistent storage at that public API origin. Never set `PUBLIC_API_BASE_URL` to a Docker service name such as `http://api:8000`; that address is private to the container network.

## Storefront behavior

- Tenant colours and fonts become site-level CSS variables and override semantic theme utilities.
- Uploaded logos, favicon, hero/about images, property placeholder, social card, and partner logos use public absolute URLs.
- Facebook, Instagram, LinkedIn, YouTube, and TikTok appear only when configured and use safe external-link attributes.
- Services, statistics, testimonials, FAQs, mission, vision, about, agents, newsletter, contact CTA, and other homepage sections respect visibility, ordering, and available content.
- Enabled pages control header/footer navigation, direct route access, internal company links, and the tenant sitemap.
- Optional tenant content is hidden when absent; the public tenant never falls back to fictional demo agency details.
- Agency and property metadata, Open Graph data, favicon, organization JSON-LD, property JSON-LD, and tenant sitemap are generated from published data.

## Migration behavior

Migration `0010_website_published_snapshot` adds the published snapshot, completion percentage, and version fields. It keeps existing published agencies live and snapshots their legacy public configuration. New agencies remain unpublished by default.

## Deployment checklist

1. Apply Django migrations.
2. Set public CRM, API, and storefront origins in environment configuration.
3. Ensure CORS and CSRF trusted origins contain the CRM/storefront origins where applicable.
4. Serve persistent media at `PUBLIC_API_BASE_URL/media/` or configure the storage backend to return public object URLs.
5. Build and deploy the CRM and storefront after the API migration.
6. Upload, preview, publish, and reload a test tenant before enabling onboarding for customers.
