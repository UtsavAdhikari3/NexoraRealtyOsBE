# Agency website creator

## Product flow

The website creator turns the agency registration profile into a dedicated public website. New agencies start unpublished. After login, an owner or manager whose website setup is incomplete is sent to `/onboarding/website` in the CRM.

The eight-step wizard collects:

1. agency identity, contact information, service area, and business hours;
2. logo, cover image, and brand colours;
3. homepage tagline, eyebrow, headline, and introduction;
4. mission, company story, and services;
5. statistics, testimonials, and FAQs;
6. WhatsApp, Viber, and social links;
7. SEO title and description;
8. readiness review, private preview, and publishing.

Each step is independently saved, so an agency can leave and resume at its last saved step. Saving never changes the currently published site. Publishing explicitly copies `website_draft_config` to `website_config`, which makes draft editing safe for an already-live agency.

## Publishing rules

Only agency owners and managers can edit, publish, or unpublish a website. The agency must have an active paid subscription before publishing. The required fields are:

- agency name, public email, and phone;
- an agency description of at least 40 characters;
- an address or service area;
- logo and cover image;
- homepage headline and introduction;
- SEO title and an SEO description of at least 40 characters.

Images must be JPG, PNG, or WebP and no larger than 5 MB. Structured repeaters are validated and limited to 8 services, 6 statistics, 8 testimonials, and 12 FAQs.

The public website is available at `/agency/{agency-slug}`. Unpublishing immediately removes it from the public agency endpoint while retaining the draft and last published configuration.

## Preview security

The CRM receives a signed preview URL from the backend. The token contains only the agency ID, is signed with Django's secret key, and expires after 24 hours. The storefront resolves it through the public preview endpoint, marks the page `noindex`, disables template navigation, and disables search and lead submissions. It never exposes the draft through the normal public agency endpoint.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/agencies/me/website-onboarding/` | Load the saved draft, progress, readiness, and URLs |
| PATCH | `/api/agencies/me/website-onboarding/` | Save a wizard step or upload brand media |
| POST | `/api/agencies/me/website/publish/` | Validate readiness and copy the draft to the live config |
| POST | `/api/agencies/me/website/unpublish/` | Make the website private without deleting its content |
| GET | `/api/public/agencies/website-preview/?token=...` | Resolve a valid signed draft preview |
| GET | `/api/public/agencies/by-slug/{slug}/` | Resolve a published public agency website |

Login responses include `next_route`. It is `/onboarding/website` for an owner or manager whose onboarding status is not `completed`, otherwise `/dashboard`.

## Deployment configuration

Backend:

```env
STOREFRONT_PUBLIC_URL=https://template.nexorarealtyos.com
PUBLIC_FRONTEND_URL=https://crm.nexorarealtyos.com
```

CRM:

```env
VITE_STOREFRONT_URL=https://template.nexorarealtyos.com
```

Storefront:

```env
API_BASE_URL=https://api.nexorarealtyos.com/api
NEXT_PUBLIC_API_BASE_URL=https://api.nexorarealtyos.com/api
```

`STOREFRONT_PUBLIC_URL` must be the origin running `RealEstateStandAlone`, not the marketing site, CRM, or API. Apply migration `agencies.0009_agency_website_onboarding` before deploying the backend. Existing published agencies are migrated to a completed state with their current live configuration copied into the draft.

## Current v1 boundary

V1 provides one production-ready template with agency-specific content, localization controls, live listings and agents, lead capture, signed draft preview, and publish/unpublish lifecycle. Custom domains, multiple selectable templates, drag-and-drop page layout, revision history, and automated domain provisioning are intentionally deferred.
