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
| GET/POST | `/api/agents/` | List/create agents |
| GET/PATCH/DELETE | `/api/agents/{id}/` | Manage or deactivate an agent |

## Public website APIs

Public routes only expose active, paid, non-expired agencies and available published properties.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/public/agencies/{license}/` | Agency profile |
| GET | `/api/public/agencies/by-slug/{slug}/` | Agency profile by slug |
| GET | `/api/public/agencies/{license}/agents/` | Active public agents |
| POST | `/api/public/agencies/{license}/contact/` | General contact lead capture |
| GET | `/api/public/agencies/{license}/properties/` | Public property listing/search |
| GET | `/api/public/agencies/{license}/properties/filter-options/` | Filter values |
| GET | `/api/public/agencies/{license}/properties/{id}/` | Property detail |
| GET | `/api/public/agencies/{license}/properties/{id}/similar/` | Similar listings |
| POST | `/api/public/agencies/{license}/properties/{id}/inquire/` | Property inquiry |
| POST | `/api/public/agencies/{license}/properties/{id}/request-site-visit/` | Visit request |
| POST | `/api/public/agencies/{license}/properties/{id}/events/` | View/call/WhatsApp/Viber conversion event |

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

Scheduled posts require both `scheduled_at` and `social_account`. Set `target_platforms` to `['facebook', 'instagram']` for scheduled cross-posting.

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

## Error behavior

- `400`: validation failure
- `401`: missing/invalid JWT or inactive subscription
- `403`: authenticated but role is not allowed
- `404`: missing object or tenant/public visibility boundary
- `429`: request throttle exceeded
- `502`: upstream social publishing failed
