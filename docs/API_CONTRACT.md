# Backend MVP API contract

All API payloads use JSON unless uploading media. Datetimes use ISO 8601 with timezone information. Protected endpoints use `Authorization: Bearer <access-token>`.

The generated OpenAPI schema at `/api/schema/` is the source of truth for request and response field details.

## Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register/` | Register an agency owner and agency |
| POST | `/api/auth/login/` | Password login or initiate OTP verification |
| POST | `/api/auth/verify-login-otp/` | Verify email and receive JWTs |
| POST | `/api/auth/resend-login-otp/` | Resend login OTP |
| POST | `/api/auth/token/refresh/` | Rotate/refresh an access token |

Paid, active, non-expired agencies can use protected APIs. Existing JWTs are rejected when the user or subscription becomes inactive.

## Agency and agents

| Method | Endpoint | Purpose |
|---|---|---|
| GET/PATCH | `/api/agencies/me/` | Read/update current agency branding and profile |
| GET/POST | `/api/agencies/localization/` | Read localization defaults/current AD and BS dates, or convert a date between AD and BS |
| GET/POST | `/api/agents/` | List/create agents |
| GET/PATCH | `/api/agents/me/profile/` | Agent-only self-service professional profile |
| GET/PATCH/DELETE | `/api/agents/{id}/` | Manage or deactivate an agent |

Agent profiles include contact details, profile image, designation, location, experience, languages, specialties, biography, and Facebook/Instagram/LinkedIn links. `deals_closed`, `current_listing_ids`, and `sold_property_ids` are read-only values derived from properties assigned to the agent. Profile image updates use `multipart/form-data`; all other profile updates can use JSON.

## Public website APIs

Public routes only expose websites for active, paid, non-expired agencies that are published. Every public property consumer uses the same eligibility policy: the property must be published, fresh, free of pending republish approval, and in `available`, `reserved`, or `under_negotiation` status.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/public/agencies/{license}/` | Agency profile |
| GET | `/api/public/agencies/by-slug/{slug}/` | Agency profile by slug |
| GET | `/api/public/agencies/by-domain/?domain={host}` | Published agency profile by custom domain |
| GET | `/api/public/agencies/{license}/agents/` | Active public agents |
| GET | `/api/public/agencies/{license}/agents/{id}/` | Public agent profile and listing/deal summary |
| POST | `/api/public/agencies/{license}/contact/` | General contact lead capture |
| GET | `/api/public/agencies/{license}/properties/` | Public property listing/search |
| GET | `/api/public/agencies/{license}/properties/filter-options/` | Filter values |
| GET | `/api/public/agencies/{license}/properties/{id}/` | Property detail |
| GET | `/api/public/agencies/{license}/properties/{id}/similar/` | Similar listings |
| POST | `/api/public/agencies/{license}/properties/{id}/inquire/` | Property inquiry |
| POST | `/api/public/agencies/{license}/properties/{id}/request-site-visit/` | Visit request |
| POST | `/api/public/agencies/{license}/properties/{id}/events/` | View/call/WhatsApp/Viber conversion event |
| POST | `/api/public/agencies/{slug}/submissions/` | Contact, inquiry, valuation, newsletter, guide, career, or demo submission |
| POST | `/api/public/agencies/{slug}/agents/{id}/reviews/` | Submit an agent review for moderation |

The property list is page-number paginated (`page`, optional `page_size`, default 24, maximum 60) and returns `{count,next,previous,results}`. `results` use the lightweight card contract with one `primary_image`; property detail retains the rich response.

Supported listing query parameters include `property_type`, `purpose` (`sale`, `rent`, or `lease`), `location`, structured location fields, price/room/area/road/map filters, `featured`, `search`, `assigned_agent`, a maximum of 24 comma-separated `ids`, and `ordering` (`latest`, `featured`, `price_asc`, `price_desc`, or `oldest`; legacy aliases remain accepted). `ids` preserves requested order unless explicit ordering is supplied. Invalid or cross-agency agent IDs return 400.

`filter-options/` returns eligible-inventory counts in `summary`, `property_types`, `purposes`, and grouped `locations`. `similar/` returns `{count,results}` with up to six lightweight cards ranked deterministically by purpose, type, location, price, type-appropriate size/bedrooms, featured status, and recency.

Send `X-Visitor-ID` with anonymous requests when the frontend has a first-party visitor identifier. Public submissions normalize Nepal phone formats and reuse an active lead within the same agency when phone or email matches.

## Properties

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/properties/` | List/create inventory |
| GET/PATCH/DELETE | `/api/properties/{id}/` | Manage property |
| GET | `/api/properties/filter-options/` | Dashboard filter values |
| GET/POST | `/api/properties/{id}/media/` | List/upload ordered media; accepts `alt_text` and `is_public` |
| GET/PATCH/DELETE | `/api/properties/media/{id}/` | Manage media, public visibility, and primary status |

Only public statuses can remain published. Agents create drafts assigned to themselves; owners/managers control publication and deletion. Uploaded images are decoded and validated, dimensions are bounded, and the database permits only one primary media row per property. Public detail responses include only `is_public` images/videos/reels in primary/sort order; documents are private by default at the public API boundary.

## Leads and CRM

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/leads/` | Search/create accessible leads |
| GET/PATCH/DELETE | `/api/leads/{id}/` | Lead detail and stage changes |
| GET/POST | `/api/leads/{id}/interests/` | Interested properties |
| GET/POST | `/api/leads/{id}/interactions/` | Calls, notes, meetings, and follow-ups |
| POST | `/api/leads/{id}/complete-follow-up/` | Complete action and optionally schedule next one |
| GET | `/api/leads/{id}/timeline/` | Interactions, stage history, and visits |
| GET/PATCH | `/api/leads/automation/settings/` | Read or configure agency routing, capacity, SLA, reminder, and inactivity thresholds |
| GET/POST | `/api/leads/automation/rules/` | Ordered property, location, property-type, listing-agent, specific-agent, and round-robin rules |
| GET/PATCH/DELETE | `/api/leads/automation/rules/{id}/` | Manage an assignment rule |
| GET | `/api/leads/automation/dashboard/` | Workload, overdue-response, duplicate, and per-agent response metrics |
| GET | `/api/leads/automation/duplicates/` | Review detected duplicate leads; accepts a `status` filter |
| PATCH | `/api/leads/automation/duplicates/{id}/` | Confirm or dismiss a duplicate flag |
| GET | `/api/leads/automation/events/` | Recent routing, response, reminder, escalation, and reassignment events |
| POST | `/api/leads/automation/process/` | Manager-triggered escalation and inactivity check |

Use the `follow_up` list filter with `due_today`, `overdue`, `upcoming`, or `none`. Marking a lead `lost` requires `lost_reason`.

## Site visits

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/site-visits/` | List/schedule visits |
| GET/PATCH/DELETE | `/api/site-visits/{id}/` | Update outcome/status |

Cancellation requires a reason. Completing a visit records `completed_at` and moves the lead to `site_visit_completed` with status history.

## Dashboard and analytics

`GET /api/dashboard/summary/` returns property, lead, agent, view, inquiry, follow-up, visit, source, stage, and top-property metrics scoped to the agency. Agents receive metrics for their assigned leads and visits.

## Social media

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/social-posts/posts/` | Draft/schedule posts |
| GET/PATCH/DELETE | `/api/social-posts/posts/{id}/` | Manage a post |
| POST | `/api/social-posts/posts/{id}/publish/` | Publish to Facebook, Instagram, or both |
| GET | `/api/social-posts/connections/meta/start/` | Start Meta OAuth |
| GET | `/api/social-posts/connections/meta/callback/` | OAuth callback |
| GET | `/api/social-posts/accounts/` | Connected accounts |
| POST | `/api/social-posts/accounts/{id}/disconnect/` | Disconnect account |

Scheduled posts require both `scheduled_at` and `social_account`. In JSON, set
`target_platforms` to `["facebook", "instagram"]` for scheduled cross-posting;
it is an array, not a string. When uploading an image with multipart form-data,
repeat the `target_platforms` key once for each platform.

For immediate cross-posting, call:

```json
POST /api/social-posts/posts/{id}/publish/
{
  "platforms": ["facebook", "instagram"]
}
```

The selected `social_account` can be the Facebook Page account. Nexora finds the Instagram account linked to the same Page through the stored `page_id`. Instagram image posts require an uploaded JPEG and a publicly reachable HTTPS media URL. The backend creates an Instagram media container, waits for it to finish, and then publishes it.

Each target is recorded in `publish_results`. Overall statuses are:

- `published`: every requested target succeeded;
- `partial`: at least one target succeeded and another failed;
- `failed`: no target succeeded.

A retry skips already published results, preventing duplicate posts on the platform that previously succeeded. Partial responses use HTTP `207`; total upstream failure uses HTTP `502`.

## Listing distribution toolkit

Authenticated agency users can generate and download marketing assets for properties they manage. Owners and managers can also export multiple agency listings; agents are restricted to their assigned listings.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/properties/{id}/distribution/` | Captions, portal copy, asset catalogue, links, and attribution totals |
| GET/POST | `/api/properties/{id}/distribution/links/` | List or create source-tracked short links |
| PATCH/DELETE | `/api/properties/distribution/links/{id}/` | Enable, disable, edit, or remove a tracked link |
| GET | `/api/properties/{id}/distribution/assets/{type}/` | Download a social image, QR, PDF, CSV, watermarked ZIP, or full package |
| POST | `/api/properties/{id}/distribution/social-draft/` | Create a generated Meta feed-post draft; publish it through `/api/social-posts/posts/{id}/publish/` |
| GET | `/api/properties/distribution/portal-export/?ids=1,2` | Export selected listings in portal-ready CSV format |
| GET | `/api/public/s/{code}/` | Count a distribution click and redirect to the public listing with attribution |

Asset types are `facebook_post`, `instagram_post`, `instagram_story`, `watermarked_images`, `brochure`, `window_card`, `qr_code`, `portal_csv`, and `media_package`. Pass `?link={distribution_link_id}` when downloading an asset to embed that tracked URL in its QR/copy. Public inquiry and site-visit payloads accept `utm_source`, `utm_medium`, `utm_campaign`, and `distribution_code`.

## Unified social inbox

Meta sends Facebook Page and Instagram Business messaging events to `GET/POST /api/webhooks/meta/`. The GET request verifies the callback; POST requests require Meta's `X-Hub-Signature-256` signature. Payloads and messages are stored idempotently, so webhook retries do not duplicate conversations or messages.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/inbox/conversations/` | List agency conversations |
| GET | `/api/inbox/conversations/{id}/` | Get a conversation |
| GET | `/api/inbox/conversations/{id}/messages/` | Get its message history |
| POST | `/api/inbox/conversations/{id}/reply/` | Send a text reply |
| POST | `/api/inbox/conversations/{id}/assign/` | Assign or claim a conversation |
| POST | `/api/inbox/conversations/{id}/link-lead/` | Link an existing CRM lead |
| POST | `/api/inbox/conversations/{id}/create-lead/` | Create and link a CRM lead |
| POST | `/api/inbox/conversations/{id}/mark-read/` | Clear the Nexora unread count |
| PATCH | `/api/inbox/conversations/{id}/status/` | Set `open`, `pending`, `closed`, or `spam` |

Conversation list filters include `platform`, `status`, `assigned_agent`, `unread`, and `search`. Agency owners can access every conversation in their agency. Agents can access conversations assigned to them and unassigned conversations; an agent may claim an unassigned conversation but cannot assign it to another agent.

Set `META_WEBHOOK_VERIFY_TOKEN` to a long random value and use that same value in the Meta dashboard. Configure the callback URL as `https://<public-backend-host>/api/webhooks/meta/`. Reconnect existing Meta accounts after deploying this feature so Nexora can request messaging permissions and subscribe the Page to webhook fields.

## Operations, transactions, and customer portal

Agency-authenticated resources use standard list/create and `{id}` retrieve/patch/delete routes below `/api/operations/`: `contacts`, `owners`, `deals`, `offers`, `documents`, `leases`, `tasks`, `appointments`, `availability`, `invitations`, `team-members`, `notifications`, `custom-fields`, `pipeline-stages`, and `audit-logs`.

Additional endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/operations/reports/summary/` | Pipeline, lead source, and agent performance report |
| GET | `/api/operations/matching/leads/{id}/` | Ranked property matches for a lead |
| GET | `/api/operations/properties/compare/?ids=1,2` | Compare up to four agency properties |
| POST | `/api/operations/invitation/accept/` | Accept a one-time team invitation |
| POST | `/api/operations/subscriptions/checkout/` | Create Stripe Checkout session |
| POST | `/api/operations/subscriptions/billing-portal/` | Open Stripe billing portal |
| POST | `/api/webhooks/stripe/` | Receive signature-verified Stripe events |
| GET | `/api/operations/admin/summary/` | Super-admin platform metrics |
| GET/PATCH | `/api/operations/platform-agencies/{id}/` | Super-admin agency controls |

Customer endpoints live under `/api/public/agencies/{slug}/`. Register or log in under `customers/`, then send the returned token in `X-Customer-Token` for saved properties and saved searches. Saved-property reads and writes use the authoritative public eligibility policy. Public appointment availability and booking use `appointments/`; POST accepts only an eligible same-agency property and active same-agency agent, forces `requested` status, and is throttled. Canonical public listing lookup uses `/api/public/agencies/by-slug/{slug}/listings/{share_slug}/` and the same eligibility policy.

Public inquiry, property event, site-visit, generic submission, saved-property, appointment, distribution-link, and saved-search alert property references all use the same public eligibility selector. Public event metadata is limited to a 2 KB JSON object; generic submission metadata to a 4 KB JSON object and message text to 8 KB. Site-visit preferred times must be in the future.

## Agency website creator

Owners and managers build the public agency storefront using a separate draft configuration. A normal save never changes the live website; publishing validates readiness and copies the draft into the public configuration.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/agencies/me/website-onboarding/` | Get draft content, current step, completion, missing fields, and preview/public URLs |
| PATCH | `/api/agencies/me/website-onboarding/` | Save profile fields, brand uploads, and `website_draft_config` |
| POST | `/api/agencies/me/website/publish/` | Publish a complete draft for a paid agency |
| POST | `/api/agencies/me/website/unpublish/` | Remove the site from public discovery while retaining content |
| GET | `/api/agencies/me/website/versions/` | List immutable publish history |
| GET | `/api/agencies/me/website/versions/{version}/` | Read a published snapshot |
| POST | `/api/agencies/me/website/versions/{version}/restore/` | Republish a historical snapshot as a new version |
| GET/POST | `/api/agencies/me/website/domains/` | List or claim normalized custom domains |
| POST | `/api/agencies/me/website/domains/{id}/verify/` | Check the exact DNS TXT ownership challenge |
| POST | `/api/agencies/me/website/domains/{id}/primary/` | Select a verified active canonical domain |
| DELETE | `/api/agencies/me/website/domains/{id}/` | Release a claimed domain |
| GET | `/api/public/agencies/website-preview/?token=...` | Return an unpublished draft for a valid 24-hour signed preview token |
| GET | `/api/public/agencies/{license}/sitemap.xml` | Tenant sitemap from enabled pages and public inventory |
| GET | `/api/public/agencies/{license}/robots.txt` | Tenant indexing policy and canonical sitemap reference |

Autosave PATCH may use `{ "base_revision": 4, "changes": { ... } }`. A stale base returns `409` with `current_revision` and the current serialized editor state. Arrays replace atomically; nested objects merge recursively. The response includes `template_capabilities`, revision metadata, and readiness capability errors. Public bootstrap responses include `canonical_base_url`, support `ETag`/`If-None-Match`, and use short revalidation caching. Property detail includes `canonical_url`.

Domain verification proves control only. The hosting platform must still provision host routing and TLS. See `docs/WEBSITE_ONBOARDING.md` for validation and deployment configuration.

## Error behavior

- `400`: validation failure
- `401`: missing/invalid JWT or inactive subscription
- `403`: authenticated but role is not allowed
- `404`: missing object or tenant/public visibility boundary
- `429`: request throttle exceeded
- `502`: upstream social publishing failed
