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

Public routes only expose active, paid, non-expired agencies and available published properties.

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

Supported listing query parameters include `property_type`, `purpose`, `location`, `province`, `district`, `city`, `price_min`, `price_max`, `bedrooms`, `bathrooms`, `furnishing_status`, `facing_direction`, `land_area_min`, `land_area_max`, `road_access_min`, `featured`, `search`, and `ordering` (`price`, `-price`, `newest`, `oldest`).

Send `X-Visitor-ID` with anonymous requests when the frontend has a first-party visitor identifier. Public submissions normalize Nepal phone formats and reuse an active lead within the same agency when phone or email matches.

## Properties

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/properties/` | List/create inventory |
| GET/PATCH/DELETE | `/api/properties/{id}/` | Manage property |
| GET | `/api/properties/filter-options/` | Dashboard filter values |
| GET/POST | `/api/properties/{id}/media/` | List/upload media |
| GET/PATCH/DELETE | `/api/properties/media/{id}/` | Manage media |

Only `available` properties can remain published. Agents create drafts assigned to themselves; owners/managers control publication and deletion.

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
| POST | `/api/properties/{id}/distribution/social-draft/` | Create or immediately publish a generated Meta feed post |
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

Customer endpoints live under `/api/public/agencies/{slug}/`. Register or log in under `customers/`, then send the returned token in `X-Customer-Token` for saved properties and saved searches. Public appointment availability and booking use `appointments/`. Canonical public listing lookup uses `/api/public/agencies/by-slug/{slug}/listings/{share_slug}/`.

## Error behavior

- `400`: validation failure
- `401`: missing/invalid JWT or inactive subscription
- `403`: authenticated but role is not allowed
- `404`: missing object or tenant/public visibility boundary
- `429`: request throttle exceeded
- `502`: upstream social publishing failed
