# Nexora RealtyOS Product Operating Flow

Date: 2026-08-09
Branch reviewed: feature/complete-public-template
Scope reviewed: Django backend (`NexoraRealtyOsBE`), agency React frontend (`NexoraFE`), standalone Next.js storefront (`RealEstateStandAlone`).

Important boundary: this document describes current behavior found in code. When something is a product assumption or recommendation, it is marked as such. Property sale payments are intentionally out of scope for the real estate transaction flow; the Stripe code in the system is for SaaS agency subscription billing, not for buying property through Nexora.

## 1. Executive System Overview

Nexora RealtyOS is a multi-tenant operating system for real estate agencies in Nepal. It helps an agency run the full listing-to-lead-to-deal workflow from one place: agency setup, team access, property onboarding, verification, listing freshness, public website publishing, lead capture, lead assignment, follow-ups, site visits, documents, offers, deals, leases, reporting, and marketing distribution.

The product has three major surfaces:

- Backend API: Django REST Framework app in `NexoraRealtyOsBE`. It owns authentication, tenant isolation, business rules, persistence, scheduled commands, public APIs, integrations, and media generation.
- Agency dashboard: React/Vite app in `NexoraFE`. Agency owners, managers, agents, and super admins use it to operate the business.
- Public storefront: Next.js app in `RealEstateStandAlone`. Public buyers, tenants, property owners, and visitors use it to browse listings, submit inquiries, request visits, save properties, create saved searches, and interact with agency public content.

The system solves a specific Nepal real estate operating problem: agencies often publish listings across Facebook, Instagram, WhatsApp, Viber, local portals, printed cards, and direct calls, while tracking verification, owner confirmation, lead ownership, follow-ups, and availability manually. Nexora turns those scattered actions into one workflow where a property is created once, verified and refreshed, distributed everywhere, and every inquiry becomes accountable CRM work.

Primary users:

- Platform super admin: manages agencies, activation, subscription status, and platform-level visibility.
- Agency owner: owns agency setup, subscription, team, approvals, verification policy, reports, and high-risk deletes.
- Agency manager: manages agents, listings, CRM workflow, republish approvals, public submissions, reviews, and automation.
- Agent: handles assigned properties, leads, conversations, site visits, tasks, documents, and follow-ups.
- Marketing user or coordinator: uses the distribution toolkit and social publishing areas. In code this is not a separate role; it is normally owner/manager/agent depending on permissions.
- Public visitor: browses agency website and listings, sends inquiries, requests site visits, reports listings, submits contact/valuation/career/newsletter/demo forms.
- Public customer account: registers per agency, saves properties, saves searches, and requests appointments.
- Property owner or seller: not modeled as a self-service listing creator. In current code, the agency creates the property; owner data is represented through `Owner`, `Contact`, documents, verification notes, and property owner relationships.

Plain-English lifecycle:

1. An agency registers and becomes active only after subscription/payment status allows access.
2. Owners or managers invite agents and configure agency profile, website, localization, fields, and pipeline stages.
3. The agency creates properties, uploads media, fills Nepal-specific land/address data, verifies documents, and publishes only listings that are current enough.
4. Published listings appear on public APIs and storefront pages only if the agency is active, paid, and the listing is published, publishable, verified for freshness, and not expired.
5. Distribution tools create captions, social images, PDFs, QR codes, watermarked media, short tracked links, and portal CSV exports.
6. Visitors arrive from website/search/social/portal/direct share links, view property pages, submit inquiries, request site visits, or report listings.
7. Public inquiries create or reuse leads, attach property interests, record interactions, run assignment automation, record attribution events, and notify the responsible people.
8. Agents work leads through conversations, interactions, follow-ups, site visits, offers, deals, documents, tasks, and leases.
9. Background jobs keep the system honest: expiring stale listings, reminding about follow-ups and site visits, escalating neglected leads, reassigning inactive leads, sending saved-search alerts, and publishing scheduled social posts.
10. Dashboards and reports read the accumulated state: properties, leads, events, site visits, deals, tasks, notifications, attribution, and agent performance.

## 2. Architecture

High-level architecture:

```text
Public visitors and customers
  -> Next.js storefront (`RealEstateStandAlone/app/agency/[agencySlug]/*`)
  -> Django public API (`/api/public/...`)
  -> PostgreSQL models owned by `Agency`
  -> lead automation, notifications, events, saved searches, appointments

Agency staff
  -> React dashboard (`NexoraFE/src/routes/index.jsx`)
  -> Axios service layer (`NexoraFE/src/services/*`)
  -> authenticated Django API (`/api/auth`, `/api/properties`, `/api/leads`, `/api/operations`, `/api/inbox`, `/api/social-posts`)
  -> PostgreSQL tenant-scoped data
  -> scheduler, Meta, Stripe, email, media/PDF/image generation

Scheduled service
  -> Django management commands from `docker-compose.yml`
  -> automation and notification side effects

External services
  -> Stripe for agency subscription billing only
  -> Meta Graph API for Facebook/Instagram accounts, publishing, and messaging webhooks
  -> SMTP email for OTP, password reset, reminders, invites, and saved-search alerts
```

Main backend URL map from `realtyos/urls.py`:

- `/api/auth/`: registration, login, OTP, refresh, password reset.
- `/api/agencies/`: current agency profile and localization.
- `/api/properties/`: authenticated listing CRUD, media, verification, freshness, duplicates, distribution.
- `/api/agents/`: agent list/detail and self profile.
- `/api/leads/`: lead pipeline, interests, interactions, documents, workspace, automation.
- `/api/site-visits/`: authenticated site visit operations.
- `/api/operations/`: contacts, owners, deals, offers, documents, leases, tasks, notifications, invitations, team, platform agencies, custom fields, pipeline stages, reports, matching, comparison, appointments, subscriptions, public submission moderation, reviews.
- `/api/social-posts/`: social drafts, account connection, publishing, disconnection.
- `/api/inbox/`: Meta conversation inbox, messages, replies, assignment, lead linking.
- `/api/public/`: public agency, listing, inquiry, site visit, customer, appointment, review, submission, short-link, and analytics-event endpoints.
- `/api/webhooks/meta/`: Meta inbound messaging webhook.
- `/api/webhooks/stripe/`: Stripe subscription webhook.
- `/api/dashboard/summary/`: agency dashboard metrics.

Infrastructure from `docker-compose.yml`:

- `db`: PostgreSQL 16 with persistent volume.
- `api`: Django/Gunicorn service on port 8000; waits for DB, runs migrations, collects static, serves API/media.
- `scheduler`: same backend image, loops every 300 seconds running lead automation, reminders, saved search alerts, listing freshness, and social post publishing.
- `storefront`: Next.js standalone app on port 3000, configured with internal and public API base URLs.

## 3. User Roles

Super admin:

- Accesses platform-wide views such as `PlatformAgencyViewSet` and `admin_summary`.
- Can view or update agencies beyond a single tenant.
- Is exempt from agency subscription checks in `AgencyJWTAuthentication`.

Agency owner:

- Registers the agency, receives role `agency_owner`, manages billing/subscription, agency settings, localization, website content, team access, invitations, listings, approvals, and reports.
- Must remain active; `TeamMemberViewSet.perform_update` prevents removing or demoting the final active owner.

Agency manager:

- Similar operational powers to owner for most agency workflows, including automation settings, duplicate review, verification/freshness, invitations, agent reviews, and record deletes.

Agent:

- Can work assigned leads, assigned listings, site visits, contacts related to assigned leads, assigned deals, assigned leases, tasks, and their own public profile.
- In several viewsets, agents are automatically restricted to records assigned to them.
- Agents cannot assign/reassign leads through `LeadSerializer.validate_assigned_agent`.

Public visitor:

- Uses storefront/public routes without JWT.
- Can browse only active, paid, published, fresh listings.
- Can submit inquiries, viewing requests, reports, reviews, contact/valuation/buyer guide/newsletter/career/demo forms, and analytics events.

Public customer account:

- Belongs to one agency through `CustomerProfile`.
- Authenticates with an `X-Customer-Token`, not JWT.
- Can save/unsave properties, save searches, and request appointments.

## 4. Major User Journeys

### Agency onboarding and login

User action:

1. Owner opens dashboard registration in `NexoraFE/src/pages/auth/RegisterPage.jsx`.
2. Frontend calls `POST /api/auth/register/` through `authService.js`.
3. `RegisterView` validates through `RegisterSerializer` and creates an `Agency` plus an owner `AgencyUser`.
4. Login is blocked until the agency's payment/subscription state allows access.
5. Owner logs in via `POST /api/auth/login/`.
6. `LoginView` checks credentials, agency link, payment status, active subscription, and email verification.
7. If email is not verified, `send_login_verification_otp` creates `EmailOTP` and sends email; frontend routes to OTP verification.
8. `VerifyLoginOTPView` marks OTP used, marks user verified, and returns JWT access/refresh tokens.
9. `NexoraFE/src/lib/axios.js` attaches the access token to later API calls and refreshes once on 401.

Data changed:

- `Agency`, `AgencyUser`, `EmailOTP`.
- JWT token blacklist/rotation is handled by SimpleJWT.

Downstream effects:

- Agency status controls every authenticated request through `AgencyJWTAuthentication`.
- Public listing APIs also require paid/active agency state.

Failure cases:

- Invalid credentials return 401.
- Unpaid agency returns 403 with `payment_required`.
- Inactive/expired subscription returns 403/AuthenticationFailed.
- OTP expires, exceeds attempts, or is reused.
- Password reset intentionally returns a generic response whether the account exists or not.

### Agency profile, localization, and website setup

User action:

1. Owner/manager opens settings/website pages in the dashboard.
2. `agencyService.js` calls `GET/PATCH /api/agencies/me/`; localization controls call `GET/POST /api/agencies/localization/`.
3. `CurrentAgencyView` updates branding, contact, website, SEO, custom domain, address fields, and public website settings.
4. `LocalizationView` updates default language, AD/BS preference, Nepali digits, Nepal timezone, and message templates.
5. Next.js storefront fetches agency data using `fetchPublicAgencyBySlug` or `fetchPublicAgencyByDomain`.

Data changed:

- `Agency` fields: branding, address hierarchy, social links, website config, publication flag, default language/date/digits/timezone, message templates.

Downstream effects:

- Public pages, PDFs, captions, reminders, phone/address display, SEO metadata, and agency website availability are affected.
- Custom domain routing in `RealEstateStandAlone/app/page.tsx` depends on public agency lookup by domain.

Failure cases:

- Public agency APIs only show active, paid, published agencies.
- Unsupported localization values are rejected by backend validation.

### Property creation, Nepal data, media, and publication

User action:

1. Owner/manager/agent opens `/properties/add` in `NexoraFE`.
2. Multi-step form components under `src/pages/properties/add/steps/*` collect core listing data, Nepal address/land fields, utilities, media, description, and publication settings.
3. `propertyService.createProperty` calls `POST /api/properties/`.
4. `PropertyListCreateView.perform_create` saves the listing under the user's agency.
5. If user is an agent, backend forces `assigned_agent=user`, `status=draft`, `is_published=False`, and `is_featured=False`.
6. `Property.save` computes `land_area_sqft`, creates a `share_slug`, hides unpublishable statuses, sets `published_at` when first published, sets initial freshness dates when published, and hides expired/republish-required listings.
7. Backend records `PropertyHistory(created)` and runs `detect_duplicate_listings`.
8. Frontend uploads media through `POST /api/properties/{id}/media/`.

Data changed:

- `Property`, `PropertyMedia`, `PropertyHistory`, maybe `PropertyDuplicateFlag`.

Downstream effects:

- Public storefront may show the listing only if publishable and fresh.
- Dashboard property counts update.
- Distribution toolkit can generate assets once property exists.
- Matching, comparison, leads, site visits, deals, leases, documents, tasks, reports, and SEO pages can consume the listing.

Failure cases:

- Assigned agent must belong to the agency and have role `agent`.
- Area/road/distance/mohada/pichhad values must be positive and paired with units.
- Ward must be 1 to 99.
- Published listing must have status `available`, `reserved`, or `under_negotiation`.
- Withdrawn listing must include a withdrawal reason.
- Media requires file or external URL, honors size/content type restrictions, and only one primary media is allowed per property by serializer side effect.

### Property verification and due diligence

User action:

1. Staff opens a property detail page and uses `PropertyVerificationPanel.jsx`.
2. Frontend calls `GET /api/properties/{property_id}/verification/`.
3. `PropertyVerificationDetailView.get_object` calls `get_or_create_verification`, ensuring a one-to-one verification row and document checklist rows exist.
4. Staff uploads/links or marks each checklist document through `PATCH /api/properties/{property_id}/verification/documents/{document_type}/`.
5. Staff advances milestones through `PATCH /api/properties/{property_id}/verification/`.

Checklist document types:

- Lalpurja.
- Owner citizenship or company registration.
- Napi Naksa or trace map.
- Char Killa.
- Malpot receipt.
- Property-tax clearance.
- Building map approval.
- Construction-completion certificate.
- Power of attorney.
- Agency marketing authorization.

Verification milestones:

- Owner identity verified.
- Ownership document received.
- Agency physically inspected.
- Documents reviewed.
- Fully verified.

Technical rules:

- Milestones must be completed in order.
- Ownership document received requires Lalpurja not missing.
- Documents reviewed requires every document to be resolved.
- Fully verified requires every applicable document approved or not applicable.
- Uploading a file or URL on a missing checklist item automatically changes it to received unless a status is supplied.
- Approving/rejecting/not-applicable stamps `reviewed_by` and `reviewed_at`.

Data changed:

- `PropertyVerification`, `PropertyVerificationDocument`.

Downstream effects:

- Public serializers expose verification summary and labels.
- Storefront detail/cards can show trust badges and document counts.
- Distribution PDFs include verification/trust language.

Failure cases:

- Out-of-order milestones are rejected.
- Missing or unresolved docs block later verification.
- File type/size validation rejects invalid uploads.
- Staff without property permission cannot update verification.

### Listing freshness, expiry, republishing, and report-listing

User action:

1. Staff confirms availability through `POST /api/properties/{property_id}/freshness/confirm/`.
2. Backend validates `valid_for_days` between 1 and 90.
3. `confirm_listing_freshness` stamps `availability_verified_at`, `listing_expires_at`, optionally `owner_confirmed_at`, republishes if no approval block exists, and records history.
4. Scheduler runs `process_listing_freshness` every 300 seconds in Docker.
5. Expiring listings create in-app notifications; expired listings are hidden and marked as requiring republish approval.
6. Agents can request republishing; owners/managers approve or reject through republish endpoints.
7. Public visitors can report a listing through storefront report UI; backend creates `PublicSubmission(kind=listing_report)`, notifies staff, and writes property history.

Data changed:

- `Property.availability_verified_at`, `listing_expires_at`, `owner_confirmed_at`, `is_published`, `requires_republish_approval`, `republish_*`, `PropertyListingReminder`, `PropertyHistory`, `Notification`, `PublicSubmission`.

Downstream effects:

- Public APIs automatically hide expired listings.
- Distribution links may still redirect, but the target public listing may fail if no longer visible.
- Reports and dashboard published counts change.
- Rejected republish keeps listing hidden and stores rejection reason.

Failure cases:

- Expired listings cannot remain public because `Property.save` and public querysets enforce freshness.
- Republish decision requires pending status and owner/manager role.
- Rejection requires a reason.

### Listing distribution and social publishing

User action:

1. Staff opens distribution panel on a property detail page.
2. `propertyDistributionService.js` calls `GET /api/properties/{property_id}/distribution/`.
3. Backend returns public URL, captions, portal ad text, asset types, existing tracked links, and attribution summary.
4. Staff creates short links with source/medium/campaign.
5. Staff downloads social images, story image, watermarked media, brochure PDF, window card PDF, QR code, portal CSV, or full media package.
6. Staff can create a social draft from a property and connected Meta account through `POST /api/properties/{property_id}/distribution/social-draft/`; optionally publish immediately.

Data changed:

- `PropertyDistributionLink` for tracked links.
- `PropertyEvent(EVENT_DISTRIBUTION_CLICK)` on short-link redirect.
- `SocialPost` and `SocialPublishResult` if social drafts/publishing are used.

Downstream effects:

- UTM fields and distribution code flow into public inquiries/site visit requests and property events.
- Attribution summary in distribution panel updates from property events.
- Social post status affects marketing page and scheduled publisher.

Failure cases:

- Asset type, language, and date system are validated.
- Instagram publishing requires public HTTPS image URL and JPEG constraints.
- Meta failures result in failed/partial social post status rather than silent success.
- Published social media has immutability rules: Instagram caption edits are rejected; replacing media after publish is blocked.

### Public website browsing and inquiry

User action:

1. Visitor opens the agency's tenant URL (locally `/?tenant={agencySlug}`, in production usually `{agencySlug}.nexorarealtyos.com`) or a custom domain.
2. Next.js fetches agency data through `/api/public/agencies/by-slug/{slug}/` or `/api/public/agencies/by-domain/`.
3. Listing pages call `/api/public/agencies/{license_number}/properties/`.
4. Public queryset filters to active, paid agencies with active subscription and listings that are `is_published=True`, status `available/reserved/under_negotiation`, `availability_verified_at` set, and `listing_expires_at` in the future.
5. Visitor views a detail page and can trigger analytics events through `/properties/{id}/events/`.
6. Visitor submits inquiry through `/properties/{id}/inquire/`.
7. Backend reuses or creates a lead, links property interest, creates an inbound interaction, records property event, stores attribution, and returns lead status/assignment.

Data changed:

- `PropertyEvent`, `Lead`, `LeadPropertyInterest`, `LeadInteraction`, `LeadStatusHistory` for new leads, lead `custom_data`.

Downstream effects:

- Assignment automation may assign the lead and notify agent.
- Dashboard inquiry/event counts update.
- Distribution attribution can prove which source generated inquiry.
- Lead appears in CRM, inbox/workspace, reports, and matching.

Failure cases:

- Non-public/stale/unpaid/inactive listings return 404 through queryset filtering.
- Duplicate public lead creation is avoided by normalized phone/email matching against non-lost/non-archived leads.
- Invalid inquiry payload is rejected by serializer validation.

### Unified lead inbox and Meta messaging

User action:

1. Agency connects Meta from social media page.
2. `MetaConnectionStartView` creates `SocialOAuthState` and returns Meta OAuth URL.
3. Callback exchanges code for tokens, fetches Facebook pages, creates/updates `SocialAccount` rows for Facebook and Instagram, and attempts webhook subscription.
4. Meta sends messaging webhooks to `/api/webhooks/meta/`.
5. `record_and_process_webhook` stores idempotent `WebhookEvent` by payload hash.
6. `ingest_messaging_event` finds the receiving account, creates/updates `SocialContact`, `Conversation`, and `SocialMessage`, increments unread count, and if linked to a lead, creates `LeadInteraction`.
7. Staff uses `/inbox` in `NexoraFE`, which calls `/api/inbox/conversations/`, messages, reply, assign, link-lead, create-lead, mark-read, and status endpoints.

Data changed:

- `SocialOAuthState`, `SocialAccount`, `WebhookEvent`, `SocialContact`, `Conversation`, `SocialMessage`, optionally `Lead` and `LeadInteraction`.

Downstream effects:

- Linked conversations contribute unread counts to lead serializers and lead workspace.
- Inbound messages update lead contact/activity context.
- Replies send through Meta using `send_meta_text_message` and create outbound message records.

Failure cases:

- Webhook signature validation can reject invalid Meta calls.
- Duplicate webhook payloads and duplicate provider message IDs are ignored safely.
- Unknown receiving account causes event to be skipped.
- Meta send failures mark message failed or return API error depending on endpoint.

### Lead management and rule-based automation

User action:

1. Staff creates or updates leads from `/leads`, `/inbox`, public forms, or site visits.
2. `LeadListCreateView.perform_create` saves agency/user context and creates status history.
3. `apply_lead_automation` runs unless disabled.
4. Assignment rules are checked by priority against property, location, and property type.
5. Assignment can use specific agent, listing agent, round robin, fallback listing agent, fallback round robin, or leave unassigned.
6. The system respects max active leads per agent.
7. Duplicate lead detection creates manager notifications.
8. Scheduler escalates missed response SLA, alerts managers about neglected leads, and reassigns inactive leads when enabled.

Data changed:

- `Lead`, `LeadStatusHistory`, `LeadAutomationSettings`, `LeadAssignmentRule`, `LeadDuplicateFlag`, `LeadAutomationEvent`, `Notification`.

Downstream effects:

- Agent dashboards and filters change.
- Lead workspace aggregates conversations, interactions, site visits, deals, offers, docs, automation events, and duplicate flags.
- Response time reporting depends on outbound non-internal interactions from assigned agents.

Failure cases:

- Agents cannot assign/reassign leads.
- Invalid pipeline/custom stages are rejected unless configured as `PipelineStage`.
- Lost leads require `lost_reason`.
- Escalation and reassignment require scheduler execution.
- Automation uses database transactions and row locking around settings to protect round-robin cursor.

### Contacts, owners, deals, offers, leases, documents, tasks

User action:

1. Staff uses pages such as contacts, owners, deals, offers, documents, leases, tasks, calendar, appointments, matching, comparison, and reports.
2. `operationsService.js` maps most of these to `AgencyModelViewSet` resources under `/api/operations/{resource}/`.
3. All normal records are agency-scoped; super admin can query across agencies where implemented.
4. Agents see restricted subsets.
5. Creating records writes audit logs and may create notifications.

Important behavior:

- Contacts can be imported from leads through `POST /api/operations/contacts/import-leads/`.
- Deals can link lead, contact, property, assigned agent; creating assigned deal notifies agent.
- Accepted offer changes its deal value and moves deal stage to `contract`.
- Deal save sets `closed_at` only for `closed_won` and clears it for non-closed stages.
- Lease validates end date after start date and rent payment day 1 to 28.
- Task save sets/clears `completed_at` based on status.
- Documents can attach to lead, property, deal, contact, owner and honor media upload limits.

Data changed:

- `Contact`, `Owner`, `Deal`, `Offer`, `Document`, `Lease`, `Task`, `Notification`, `AuditLog`.

Downstream effects:

- Reports read deal stages, values, commission, lead sources, task status.
- Lead workspace reads linked deals/offers/documents/contact docs.
- Agent workload and task reminders depend on assignments.

Failure cases:

- AgencyValidationMixin rejects cross-agency related records.
- Custom data is validated against agency custom fields.
- Deletes in generic operations require owner/manager role.

### Customer accounts, saved properties, saved searches, appointments

User action:

1. Visitor opens storefront customer portal.
2. Customer registers or logs in through public endpoints under `/api/public/agencies/{slug}/customers/`.
3. Frontend stores `access_token` in local storage and sends it through `X-Customer-Token`.
4. Customer toggles saved properties and creates saved searches.
5. Scheduler sends saved-search alert emails when newly created published properties match saved filters.
6. Customer or visitor requests appointments from availability slots.

Data changed:

- `CustomerProfile`, `SavedProperty`, `SavedSearch`, `Appointment`, `Notification`.

Downstream effects:

- Saved searches consume property creation/publication data.
- Appointments notify agents and appear in agency appointment/calendar pages.
- Customer saved property state is agency-specific.

Failure cases:

- Duplicate customer email per agency is blocked.
- Invalid customer token returns 404 via `customer_from_request`.
- Saved property toggle deletes existing saved row on second post.
- Appointment agent/property must belong to the agency.

## 5. Feature Inventory

Core platform:

- Multi-tenant agency accounts and subscription gating.
- JWT authentication, OTP email verification, token refresh, password reset.
- Role-based access for super admin, owner, manager, agent.
- Agency branding, website settings, custom domain data, website publication.
- Nepal localization: language, AD/BS date handling, Nepal timezone, Nepali digits, lakh/crore, phone/address formatting, message templates.
- Team members, invitations, agent profiles.
- Audit logs for operations and middleware-tracked modules.

Property and listing:

- Property CRUD, assignment, draft/published/status workflow.
- Nepal property data model: Ropani/Aana/Paisa/Daam, Bigha/Kattha/Dhur, sqft/sqm conversion, price per area, lakh/crore formatting, province/district/municipality/ward/tole, landmark, road width/type, facing, mohada/pichhad, plot shape, utilities, major road distance, land classification.
- Media uploads with primary image ordering.
- Verification checklist and milestone workflow.
- Freshness confirmation, expiry, republish approval, duplicate detection, public report listing, property history.
- Public listing search, filters, detail, similar properties, events, map bounds.
- Distribution toolkit: captions, QR, tracked links, source attribution, social images, watermarked media, PDF brochure/window card, portal CSV, media package.

CRM and sales/rent operations:

- Leads, statuses, sources, budgets, preferences, custom data.
- Lead property interests and communication history.
- Unified lead workspace.
- Rule-based lead automation, duplicate lead detection, SLA tracking, escalation, manager alerts, reassignment.
- Unified Meta inbox with social contacts, conversations, messages, reply, lead linking.
- Site visits from internal and public flows, reminders, status-driven lead updates.
- Contacts, owners, deals, offers, documents, leases, tasks, notifications.
- Matching and property comparison.
- Reports, dashboard summary, agent performance.

Public website/customer:

- Agency public pages, agent directory, company/story/mission/FAQ/careers/contact/valuation pages.
- Public forms and submissions.
- Moderated agent reviews.
- Customer registration/login, saved properties, saved searches, appointment booking.
- Analytics events for property views and contact clicks.

Integrations:

- Meta OAuth, Facebook/Instagram account connection, publishing, deletion/edit constraints, messaging webhooks.
- Stripe subscription checkout, billing portal, signed webhooks, payments history.
- Email for OTP, password reset, invitations, reminders, saved-search alerts.

## 6. Detailed Feature Analysis

### Authentication and agency access

Purpose: protect the agency dashboard and make tenant isolation enforceable.

Entry points: `LoginPage`, `RegisterPage`, `VerifyLoginOTPPage`, `ResetPasswordPage`; services in `authService.js`; backend `users/views.py`.

Technical flow:

- Registration creates agency and owner.
- Login returns JWT only after credential, agency, payment, subscription, and email verification checks.
- `AgencyJWTAuthentication` re-checks subscription on every authenticated request.
- Axios adds `Authorization: Bearer` and refreshes once.

Data: `AgencyUser`, `Agency`, `EmailOTP`, JWT blacklist tables.

Dependencies: agency payment/subscription fields, email backend, SimpleJWT.

Side effects: login can send OTP; password reset can send email.

Test when modified: login, OTP, token refresh, unpaid agency, expired subscription, super admin login, password reset, protected route redirects.

### Agency and localization

Purpose: let each agency control public identity and Nepal-specific display defaults.

Entry points: settings and website pages; `agencyService.js`; `/api/agencies/me/`, `/api/agencies/localization/`.

Technical flow:

- `CurrentAgencyView` exposes and patches agency profile fields.
- `LocalizationView` resolves language/date/digit/timezone settings and templates.
- `agencies/localization.py` formats dates, numbers, currency, phone, addresses, and message templates.

Data: `Agency` profile fields, localization defaults, `message_templates`.

Dependencies: public serializers, distribution PDFs/captions, reminders, storefront localization provider.

Failure: invalid defaults rejected; missing templates fall back to defaults.

Test when modified: public agency API, distribution assets, reminders, Settings page, storefront language/date/digit switching.

### Property data and lifecycle

Purpose: make listings suitable for Nepal and reliable enough for public trust.

Entry points: dashboard property list/detail/add/edit; public listing pages.

Technical flow:

- Dashboard CRUD calls `/api/properties/`.
- `PropertySerializer` validates units, status, assignment, publishability, custom data.
- `Property.save` computes derived fields and enforces publication constraints.
- Public APIs read only fresh published records.

Data: `Property`, `PropertyMedia`, `PropertyHistory`, `PropertyEvent`.

Dependencies: agents, agency status, localization, media, verification, freshness, leads, distribution.

Failure: invalid units, missing withdrawal reason, invalid publication status, expired listing hidden.

Test when modified: property create/edit, public listing visibility, area conversions, property filters, distribution, lead matching, saved-search alerts.

### Verification

Purpose: give agencies a repeatable due-diligence workflow and a public trust signal.

Entry points: `PropertyVerificationPanel.jsx`, verification endpoints.

Technical flow:

- `get_or_create_verification` seeds checklist rows.
- Document serializer auto-marks received and stamps reviewers.
- Verification serializer enforces ordered milestones and document completion.

Data: `PropertyVerification`, `PropertyVerificationDocument`.

Dependencies: property permissions, media upload rules, public serializer summaries.

Failure: milestone order, missing Lalpurja, unresolved documents, invalid file.

Test when modified: each milestone, document statuses, fully verified logic, public trust labels, permission boundaries.

### Freshness and listing trust

Purpose: prevent stale listings from being marketed publicly.

Entry points: `PropertyFreshnessPanel.jsx`, scheduler, public report listing UI.

Technical flow:

- Staff confirmation stamps verification/expiry fields.
- Scheduler creates reminders and hides expired listings.
- Republish requests require manager approval.
- Public reports create submissions and history.

Data: `PropertyListingReminder`, `PropertyHistory`, `PublicSubmission`, `Notification`.

Dependencies: scheduler, notifications, public querysets, distribution links.

Failure: scheduler down means reminders/auto-expiry command does not run, although model/public queryset checks still protect visibility when records are saved or queried.

Test when modified: expiry windows, public visibility, republish approval/rejection, report listing, notifications.

### Lead inbox and automation

Purpose: turn all inquiry sources into accountable lead ownership and follow-up.

Entry points: `/leads`, `/inbox`, public inquiries, public submissions, site visit requests, Meta webhooks.

Technical flow:

- Lead CRUD runs `apply_lead_automation`.
- Rules are evaluated by priority.
- Assignment stamps response due dates and creates automation events/notifications.
- Scheduler processes escalation, neglect alert, inactive reassignment.
- Interactions update last contact and response timing.

Data: `Lead`, `LeadPropertyInterest`, `LeadInteraction`, `LeadStatusHistory`, `LeadAutomation*`, `Notification`.

Dependencies: property interests, agents, settings, scheduler, conversations, site visits, deals, reports.

Failure: no eligible agent leaves unassigned; invalid stage rejected; duplicates are flagged, not merged automatically.

Test when modified: public lead creation, manual lead creation, rules, max capacity, round robin, response tracking, escalation, manager alerts, reassignment, duplicate review.

### Site visits

Purpose: convert interest into scheduled viewing work and keep leads moving.

Entry points: `SiteVisitsPage`, public request viewing forms, appointments/customer portal separately.

Technical flow:

- Internal create defaults agent based on creator role or lead assignment.
- Public request creates/reuses lead, property interest, site visit, interaction, event.
- Updating status to scheduled/completed updates lead status history.
- Scheduling queues emails on transaction commit.

Data: `SiteVisit`, `LeadInteraction`, `LeadStatusHistory`, `PropertyEvent`.

Dependencies: leads, properties, agents, email, scheduler reminders.

Failure: public request requires active paid agency and available property; internal delete requires owner/manager; reminders require scheduler/email.

Test when modified: create, reschedule, complete, cancel, public request, lead status update, reminder reset.

### Operations CRM

Purpose: support the real business after a lead exists.

Entry points: operations pages mapped by `operationsService.js`.

Technical flow:

- `AgencyModelViewSet` scopes querysets to agency and restricts agents.
- Create/update/delete generates audit logs.
- Specific viewsets add notifications and state side effects.

Data: contacts, owners, deals, offers, documents, leases, tasks, notifications, audit logs.

Dependencies: lead/property/agent relationships and custom field definitions.

Failure: cross-agency relations rejected; lost deal requires reason; lease date/payment-day invalid; deletes owner/manager only.

Test when modified: each linked relation, agent restrictions, reports, lead workspace, notifications.

### Public storefront and customer portal

Purpose: provide a sellable agency website and lead capture surface.

Entry points: Next.js pages under `app/agency/[agencySlug]/*`.

Technical flow:

- Server components fetch agency/listings with 60-second cache.
- Forms call public APIs.
- Customer token is stored per agency in browser local storage.
- Saved searches are later processed by scheduler.

Data: public submissions, reviews, customer profiles, saved properties/searches, appointments, property events, leads.

Dependencies: agency publication/branding, public listing querysets, property freshness, email.

Failure: inactive/unpaid/unpublished agencies/listings disappear; invalid customer token fails; duplicate account email blocked.

Test when modified: dynamic agency pages, custom domain lookup, public forms, saved properties, saved searches, appointments.

## 7. Entity and Data Lifecycles

Agency:

Origin: registration, seed/admin, or platform admin.
Stored in: `agencies.Agency`.
Modified by: owner/manager through current agency endpoints; super admin through platform agencies.
Consumed by: every tenant-scoped model, public website, authentication, billing, localization, integrations.
Status: `is_active`, `payment_status`, `subscription_expires_at`, `is_website_published`.
Archive/delete: delete is not a normal product flow from code; if deleted, cascade would remove many agency-owned rows.

Property:

Origin: agency dashboard property create.
Stored in: `properties.Property`.
Modified by: owner/manager, or assigned agent with limited fields.
Consumed by: public website, distribution, leads, site visits, deals, leases, docs, reports, saved searches, comparison, matching.
Status: draft, available, reserved, under_negotiation, sold, rented, withdrawn, hidden, archived.
Archive/delete: owner/manager can delete; related cascades vary by relationship. Leases protect property deletion because `Lease.property` uses `PROTECT`.

Lead:

Origin: manual dashboard entry, public property inquiry, public site visit, public submission, inbox conversion.
Stored in: `leads.Lead`.
Modified by: assigned agent or owner/manager depending on access.
Consumed by: interactions, site visits, deals, offers, docs, contacts, reports, automation.
Status: new, contacted, interested, site_visit_scheduled, site_visit_completed, negotiating, token_booking, won, lost, follow_up_later, archived, plus agency custom stages.
Transforms into: can become `Contact`; can be linked to `Deal`, `SiteVisit`, `Document`.

Conversation:

Origin: Meta webhook or manual inbox operations.
Stored in: `crm_inbox.Conversation` and `SocialMessage`.
Modified by: Meta webhook, staff reply/status/assignment/linking.
Consumed by: inbox page, lead workspace, unread counts, lead interactions.
Status: open, pending, closed, spam.

Deal:

Origin: agency staff creates from a lead/contact/property.
Stored in: `operations.Deal`.
Modified by: assigned staff.
Consumed by: offers, documents, reports, dashboard, tasks.
Status/stage: qualified, offer, negotiation, token, contract, closed_won, closed_lost, plus agency custom stages.

Offer:

Origin: staff creates under deal.
Stored in: `operations.Offer`.
Modified by: respond action or normal updates.
Consumed by: deal detail, lead workspace, reports.
Status: draft, submitted, countered, accepted, rejected, withdrawn, expired.

Lease:

Origin: staff creates rental/lease operation record.
Stored in: `operations.Lease`.
Modified by: staff.
Consumed by: lease pages, task reminder command.
Status: draft, active, expired, terminated, renewed.

CustomerProfile:

Origin: public customer registration.
Stored in: `operations.CustomerProfile`.
Modified by: login updates last seen; saved items/searches use it.
Consumed by: public customer portal, appointment creation, saved-search scheduler.

Notification:

Origin: automation, deals, offers, tasks, site visits, appointments, reviews, submissions, freshness.
Stored in: `operations.Notification`.
Modified by: read/read-all actions.
Consumed by: notifications page, topbar counters.

## 8. Database Relationships

Business relationship summary:

- `Agency` is the tenant root. Most data has an `agency` foreign key, so normal queries must be scoped to the user's agency.
- `AgencyUser` belongs to an agency except super admin. Users are both login identities and operational assignees.
- `Property` belongs to an agency and may have an assigned agent. It is the source for public listings, marketing assets, site visits, deals, leases, documents, owners, events, saved properties, and matching.
- `PropertyMedia` belongs to property and agency. Primary image is controlled by serializer side effect.
- `PropertyVerification` is one-to-one with property; checklist documents are one-to-many from verification.
- `PropertyHistory`, `PropertyDuplicateFlag`, `PropertyListingReminder`, `PropertyEvent`, and `PropertyDistributionLink` are property-side trust/marketing/analytics records.
- `Lead` belongs to agency and may have assigned agent and creator. It is the CRM root for interactions, interests, site visits, status history, duplicate flags, automation events, deals, documents, public submissions, social contacts, and inbox conversations.
- `LeadPropertyInterest` is the junction between a lead and property; it is unique per lead/property.
- `LeadInteraction` is the communication log and also updates lead contact/response timing.
- `Contact` can be one-to-one with a lead. `Owner` can be one-to-one with contact and many-to-many with properties.
- `Deal` can link to lead, contact, property, and assigned agent. `Offer` belongs to deal. `Document` can link to several domain objects.
- `Lease` protects its property and tenant from deletion while active in the database relationship sense.
- `Task` can attach to lead, deal, or property and has assigned/created users.
- `PublicSubmission` can link to property, agent, and lead. It is the moderation queue for website forms and listing reports.
- `AgentReview` belongs to agent and requires moderation before public display.
- `CustomerProfile` belongs to agency. `SavedProperty` and `SavedSearch` belong to customer.
- `SocialAccount` belongs to agency. `SocialContact`, `Conversation`, and `SocialMessage` bridge Meta messaging into CRM.
- `Subscription`, `SubscriptionPlan`, and `Payment` handle agency SaaS billing.

Tenant isolation meaning:

- A property belonging to Agency A should never be assigned to a user from Agency B.
- A lead from Agency A should never link to a property, contact, deal, or document from Agency B.
- Most serializers and querysets enforce this either by filtering the queryset to `request.user.agency` or by `AgencyValidationMixin`.
- Public endpoints avoid JWT but enforce active/paid/published agency and listing filters.

## 9. State Machines

Property:

- draft -> available/reserved/under_negotiation -> sold/rented/withdrawn/hidden/archived.
- Only available/reserved/under_negotiation can be public.
- Expired or republish-required listings are forced hidden.
- Withdrawn requires reason and stamps `withdrawn_at`.

Property freshness:

- unconfirmed -> fresh -> expiring_soon -> expired -> republish required -> pending approval -> approved/rejected.
- Scheduler moves fresh/expiring listings toward reminders and hides expired listings.
- Manager approval can reset freshness and republish.

Verification:

- unverified -> owner_identity_verified -> ownership_document_received -> physically_inspected -> documents_reviewed -> fully_verified.
- Each milestone must be sequential.

Lead:

- new -> contacted/interested/site_visit_scheduled/site_visit_completed/negotiating/token_booking/won/lost/follow_up_later/archived.
- Custom lead stages can also be allowed through `PipelineStage`.
- Lost requires `lost_reason`.
- Site visit updates can move lead to site_visit_scheduled or site_visit_completed.

Follow-up:

- none -> pending -> completed or pending with next follow-up.
- Setting `next_follow_up_at` makes status pending.
- Completing without a next date makes status completed.

Lead automation:

- unassigned -> assigned -> awaiting response -> responded OR escalated -> neglected alert -> reassigned.
- Events are recorded in `LeadAutomationEvent`.

Conversation:

- open -> pending -> closed/spam, manually through inbox endpoint.
- Inbound Meta messages reopen a conversation.

Site visit:

- requested -> scheduled/rescheduled -> completed/cancelled/no_show.
- Scheduled and completed statuses can change lead status.

Deal:

- qualified -> offer -> negotiation -> token -> contract -> closed_won/closed_lost.
- Custom deal stages may be added.
- `closed_won` stamps `closed_at`; reopening clears it.

Offer:

- draft/submitted -> countered/accepted/rejected/withdrawn/expired.
- Accepted offer changes deal value and deal stage to contract.

Task:

- todo -> in_progress -> done/cancelled.
- Done stamps `completed_at`; reopening clears it.

Appointment:

- requested -> confirmed -> completed/cancelled.

Social post:

- draft -> scheduled -> published/partial/failed.
- Immediate publish can move directly from draft to published/partial/failed.

Subscription:

- trialing/active/past_due/cancelled/expired.
- Stripe webhooks update subscription and agency access timing.

## 10. Feature Dependency Map

Dependency graph:

```text
Authentication
  -> Agency
  -> AgencyUser
  -> Subscription/payment status
  -> Permissions and tenant scoping

Agency
  -> Users/team
  -> Properties
  -> Leads
  -> Website
  -> Localization
  -> Social accounts
  -> Billing

Properties
  -> Media
  -> Verification
  -> Freshness/history/duplicates
  -> Public website
  -> Distribution assets and links
  -> Public events and attribution
  -> Lead interests
  -> Site visits
  -> Deals/documents/leases/tasks
  -> Saved properties/searches
  -> Reports/matching/compare

Leads
  -> Assignment automation
  -> Duplicate flags
  -> Interactions
  -> Conversations
  -> Site visits
  -> Contacts
  -> Deals/offers
  -> Documents/tasks
  -> Reports/dashboard

Public storefront
  -> Public agency API
  -> Public property API
  -> Public forms
  -> Public customer APIs
  -> Analytics events

Scheduler
  -> Lead automation
  -> Follow-up/site-visit reminders
  -> Task/lease notifications
  -> Saved-search alerts
  -> Listing freshness
  -> Social publishing

External integrations
  -> Meta OAuth/social accounts
  -> Meta publishing
  -> Meta webhooks/unified inbox
  -> Stripe subscription billing
  -> SMTP email
```

If property workflows break, expect downstream impact on public listings, distribution, lead creation, site visits, deals, leases, documents, matching, compare, reports, saved searches, and analytics.

If lead workflows break, expect impact on inbox conversion, automation, follow-ups, site visits, deals, contacts, reports, dashboards, and notifications.

If agency/subscription checks break, expect either overexposure of unpaid/inactive agencies or false lockouts across the whole product.

If scheduler breaks, core CRUD still works, but reminders, auto-expiry commands, lead escalation/reassignment, scheduled publishing, and saved-search emails stop progressing.

## 11. Background Processes

Configured in Docker `scheduler`, every 300 seconds:

- `process_lead_automation`: escalates missed lead response SLAs, alerts managers, and reassigns inactive leads.
- `send_due_reminders --hours 24`: sends lead follow-up and site-visit reminder emails idempotently.
- `send_task_reminders`: creates in-app notifications for tasks due in 24 hours and leases ending within 30 days.
- `send_saved_search_alerts`: emails customers when new public listings match saved searches.
- `process_listing_freshness`: sends listing freshness notifications and hides expired listings.
- `publish_scheduled_posts`: publishes scheduled social posts.

Other automatic behavior:

- `transaction.on_commit` queues site-visit scheduled emails after successful DB commit.
- `AuditMiddleware` records successful mutations for selected API modules.
- Model `save()` methods enforce property publication visibility, task completion timestamp, deal closing timestamp, and lead interaction response tracking.
- Public short-link redirect increments click count and records distribution event.

## 12. External Integrations

Stripe:

- Used for agency subscription checkout, billing portal, webhooks, subscription state, and payment history.
- Code paths: `SubscriptionViewSet.checkout`, `SubscriptionViewSet.billing_portal`, `stripe_webhook`.
- If Stripe is not configured, checkout/billing endpoints return 503 or validation error.
- If Stripe API fails, checkout/portal return 502.
- Not used for buyer-to-seller property purchase payments.

Meta:

- Used for Facebook/Instagram OAuth, account connection, webhook subscription, post publishing, post deletion/edit operations, and messaging.
- Code paths: `social_media/views.py`, `social_media/services/meta.py`, `social_media/services/publishing.py`, `crm_inbox/services.py`.
- If Meta OAuth fails, callback returns 400/502.
- If publish fails, `SocialPublishResult` stores failed status and error message; post can become failed or partial.
- If webhooks fail signature or cannot parse, they are rejected or marked failed.

Email:

- Used for OTP, password reset, invites, lead follow-up reminders, site visit reminders, saved-search alerts.
- In development default is console backend unless SMTP configured.
- Some email failures are stored on the related model; some commands may raise if SMTP fails.

File/media/PDF/image generation:

- Media is stored through Django file fields.
- Distribution uses Pillow, qrcode, ReportLab, and Noto fonts for Nepali PDF output.
- Missing Unicode fonts can break Nepali brochure/window-card generation.

## 13. Side Effects

- Creating a property records history and runs duplicate detection.
- Saving a property can compute area sqft, generate share slug, hide unpublishable statuses, set published timestamp, set freshness expiry, and hide expired listings.
- Uploading primary property media turns other media for the same property non-primary.
- Updating a property records status/update/withdrawal history and reruns duplicate detection.
- Confirming freshness can republish a listing and records history.
- Expiry scheduler hides listings and creates reminders/notifications.
- Public listing report creates public submission, notification, and property history.
- Public inquiry creates/reuses lead, interest, interaction, event, attribution, and assignment side effects.
- Public site-visit request creates/reuses lead, interest, site visit, interaction, event, and follow-up.
- Creating/updating lead can create status history, run automation, create notifications, detect duplicates, and reset reminder fields.
- Creating non-internal lead interaction updates `last_contacted_at`; outbound assigned-agent interaction records response time.
- Updating a site visit status can update lead status and history.
- Creating a deal can notify assigned agent.
- Accepting an offer updates deal value and stage.
- Marking task done stamps completion time.
- Public submission with phone creates/reuses a lead and interaction.
- Agent review creates manager notifications and waits for moderation.
- Meta webhook can create conversations/messages and linked lead interactions.
- Short distribution link click increments click count and logs property event.
- Stripe checkout success marks agency paid and creates/updates subscription.

## 14. Impact Analysis

When changing authentication/subscription:

- Test login, OTP, token refresh, protected API, public agency/listing visibility, super admin, unpaid/expired agency behavior.

When changing `Agency` fields or localization:

- Test Settings page, public agency API, storefront layout, PDFs/captions, message templates, reminders, phone/address display.

When changing property model/serializer:

- Test property create/edit, public filters, distribution, area conversion, search, saved-search alerts, matching, compare, verification/freshness panels, media upload.

When changing public listing querysets:

- Test active paid agency, expired subscription, unpublished/stale listing, reserved/under negotiation visibility, share slug detail, similar properties, maps.

When changing verification:

- Test seeded checklist, status transitions, milestone ordering, file uploads, public trust labels, permissions.

When changing freshness:

- Test confirm endpoint, expiry scheduler, republish approval, public report listing, public visibility, notifications, property history.

When changing lead automation:

- Test public inquiry, manual lead, property interest creation, rule priority, listing agent, round robin, max capacity, duplicate detection, response time, scheduler escalation/reassignment, notifications.

When changing inbox/Meta:

- Test OAuth, accounts, webhook verify/process, duplicate payloads, message dedupe, reply, link lead, create lead, unread counts, lead workspace.

When changing operations generic viewset:

- Test every CRUD page because many pages share `AgencyModelViewSet` and `operationsService`.

When changing documents/files:

- Test property media, verification documents, operations documents, distribution media package, file size/type restrictions, public URL generation.

When changing scheduler:

- Test all six commands and production deployment loop; missed scheduler has broad operational impact.

## 15. End-to-End Scenarios

### Scenario A: Buyer discovers a listing and becomes an active lead

1. Agency publishes a fresh available property.
2. Storefront lists it through `fetchPublicProperties` -> `GET /api/public/agencies/{license}/properties/`.
3. Visitor opens detail page; storefront may call `trackPropertyEvent` -> `POST /events/`.
4. Visitor submits inquiry; frontend calls `inquireProperty`.
5. `PublicPropertyInquiryView` validates listing visibility and form payload.
6. `get_or_create_public_lead` normalizes phone/email and reuses or creates lead.
7. `apply_lead_automation` assigns agent and creates notification/event if possible.
8. Backend creates `LeadPropertyInterest`, `LeadInteraction`, `PropertyEvent`.
9. Agent sees lead in dashboard/inbox/workspace, including property interest and attribution.
10. Dashboard totals and reports reflect lead source, inquiry count, property events.

Final state: visitor is represented as a `Lead`; assigned agent has notification; property analytics and attribution are stored; public listing remains unchanged.

### Scenario B: Visitor requests a property viewing

1. Visitor submits request viewing form.
2. Next calls `/api/public/agencies/{license}/properties/{id}/request-site-visit/`.
3. Backend validates property is active, paid, published, and `status=available`.
4. Backend creates/reuses lead and assignment.
5. Backend creates hot property interest, `SiteVisit(status=requested)`, inbound site visit interaction, and property event.
6. Follow-up date is set to requested datetime.
7. Staff schedules/confirms the site visit internally.
8. Updating visit to scheduled/completed can move lead status and create `LeadStatusHistory`.
9. Reminder command sends email before visit if due.

Final state: lead has viewing workflow attached; site visit exists; property event records conversion.

### Scenario C: Property goes stale and is republished

1. Listing is published and has `listing_expires_at`.
2. Scheduler runs `process_listing_freshness`.
3. It creates 7/3/1-day reminders as applicable.
4. At expiry it creates expired reminder, hides listing, marks `requires_republish_approval=True`, records history.
5. Public APIs no longer return listing.
6. Agent requests republish.
7. Owner/manager approves; backend resets verified/expiry dates and republishes if status is publishable.

Final state: property is visible again with current confirmation, and history shows expiry/request/approval.

### Scenario D: Facebook message becomes a lead

1. Agency connects Meta account.
2. Meta webhook sends inbound message.
3. `record_and_process_webhook` stores webhook hash and calls `ingest_messaging_event`.
4. Backend creates/updates social contact, conversation, message, unread count.
5. Staff opens `/inbox`, reads conversation, and creates or links a lead.
6. Linked future inbound messages create lead interactions.
7. Staff replies; Meta send endpoint creates outbound message record and sends external message.

Final state: social message history and CRM lead are connected.

### Scenario E: Offer accepted on a deal

1. Agent or manager creates deal linked to lead/property.
2. Staff creates offer under deal.
3. Offer response endpoint accepts it.
4. Offer status becomes accepted, `responded_at` is stamped.
5. Deal `value` becomes offer amount and stage moves to `contract`.
6. Reports and pipeline values update.

Final state: negotiation moves toward contract without recording any property purchase payment.

### Scenario F: Customer saves a search and gets alerts

1. Customer registers on agency storefront portal.
2. Token stored in local browser storage.
3. Customer creates saved search with filters.
4. Agency later publishes a matching property.
5. Scheduler runs `send_saved_search_alerts`.
6. Email is sent with matching listing links and `last_notified_at` is updated.

Final state: customer gets re-engagement email based on new public listing supply.

## 16. Security and Permissions

Current safeguards:

- JWT authentication for agency dashboard APIs.
- Custom authentication rejects inactive/expired agency access after token issuance.
- Public endpoints are unauthenticated but filter aggressively by paid/active/published/fresh status.
- Agency owner/manager permissions protect agent management, deletes, automation settings, team access, duplicate review, republish approval.
- Agents are restricted in querysets for leads, site visits, operations records, conversations, and assigned properties.
- Serializers validate cross-agency relation assignments.
- Invitation acceptance uses unique UUID token and expiry.
- Password reset avoids account enumeration.
- Meta webhook supports HMAC signature validation.
- Stripe webhook uses signed payload verification.
- Public submissions and public events use throttles.

Security risks and watch areas:

- Customer portal uses long-lived `access_token` in local storage/header, not JWT/session rotation. That is simple but weaker if browser storage leaks.
- Some public APIs use license number while storefront uses slug; make sure license numbers are not treated as secrets.
- File upload validation depends on content type and size; production should add malware scanning/object storage policies if documents become sensitive.
- Subscription gating is central; regressions can lock out good agencies or expose inactive agencies.
- Public submission throttling is per DRF throttle configuration; production may need reverse-proxy/WAF controls.
- Cross-agency leakage risk is highest when adding new serializers or custom actions, because generic patterns must be followed deliberately.

## 17. Failure Handling

Validation failures:

- DRF serializers return 400 with field errors. Common cases: invalid stage, invalid related agency, missing withdrawal reason, invalid file type/size, invalid dates, invalid pipeline/custom data.

Permission failures:

- `PermissionDenied` returns 403. Common cases: agent trying manager-only work, cross-assignment, non-owner delete, non-superadmin platform admin.

Not found:

- Public hidden/unpaid/stale resources often return 404 because querysets filter them out.

External API failures:

- Meta OAuth/publish failures return 400/502 or mark results failed.
- Stripe missing config returns 503; upstream Stripe failures return 502.
- Email failures vary: invite errors are stored, some reminder commands record send errors in email helpers, some email sends may raise.

Duplicate requests:

- Public lead creation reuses existing lead by normalized phone/email when not lost/archived.
- Lead/property duplicate detection creates flags, not destructive merges.
- Meta webhook dedupes by payload hash and provider message ID.
- Saved property toggle is idempotent-ish as a toggle: second POST deletes.
- Property distribution links use unique generated code.

Background failures:

- Scheduler command failures stop or skip only the affected cycle depending on command behavior.
- Without scheduler, automatic progression stops but direct API operations still work.

Concurrent updates:

- Lead automation locks settings during assignment/round robin.
- Many normal CRUD writes do not use optimistic concurrency; last write wins.

## 18. Architectural Risks

Current behavior first:

- Business logic is spread across serializers, views, services, model `save()` methods, and management commands.
- Generic operations viewsets reduce repetition but make side effects easy to overlook.
- Public and authenticated property visibility rules are not all centralized in one service.
- Scheduler is a loop in Docker Compose, not a durable queue like Celery.
- Social publishing uses synchronous calls and polling, including short sleeps for Instagram container status.
- Customer auth is custom token-based rather than a full session/JWT implementation.
- Some endpoints use agency license number, others slug; both are valid but increase routing complexity.
- Payment/subscription code exists but product-level property transaction payments are intentionally not part of current flow.

Recommendations, separate from current behavior:

- Centralize public listing eligibility in one reusable service to avoid drift.
- Move longer-running social publishing and emails to a durable queue before high-volume production.
- Add optimistic locking or updated-at conflict checks for high-risk records like leads, properties, deals, and verification.
- Add explicit audit entries for more domain-specific events instead of relying only on generic middleware summaries.
- Add a stronger customer auth/session model if the customer portal becomes sensitive.
- Add production file scanning and private document storage for due-diligence documents.
- Add monitoring around scheduler lag, email failures, Meta failures, and webhook errors.

## 19. What Happens If...

A user is deleted/deactivated:

- Agent delete path actually sets `is_active=False`. Existing assigned records keep references. Automation eligibility excludes inactive agents, but existing assignments may remain until reassigned.

An organization/agency is deleted:

- Not a normal UI flow. Because many models use `on_delete=CASCADE`, deleting an agency would remove large amounts of tenant data. Treat as dangerous admin/data-retention operation.

An agent leaves:

- Best current path is deactivate user, then managers should reassign active leads, properties, site visits, deals, leases, and tasks. Automation can reassign inactive leads, but it does not automatically clean every module.

A customer submits the same form twice:

- Public lead flow reuses an existing non-lost/non-archived lead by normalized phone/email. It may add/keep property interest and interaction, so duplicate form submissions still add activity context.

An appointment is cancelled:

- Appointment status changes. Code does not show automatic lead/deal changes for appointment cancellation.

A site visit is cancelled:

- Site visit status changes. Lead status is only automatically changed for scheduled/completed, not cancelled.

A property is deleted:

- Owner/manager only. Related records with cascade may be deleted; leases with `PROTECT` can block deletion. Public pages/distribution links depending on it break.

A lead is reassigned:

- `stamp_assignment` resets response SLA fields, records automation event, and notifies the new agent.

A subscription expires:

- Authenticated agency requests are rejected by `AgencyJWTAuthentication`; public listing/agency APIs hide the agency/listings when expiry is in the past.

Meta stops responding:

- OAuth/publish/reply operations fail with 502 or failed status. Existing CRM data remains.

Scheduler goes offline:

- Lead escalation/reassignment, reminders, saved-search alerts, scheduled publishing, and freshness command stop. Public querysets still hide already-expired listings when queried, but reminder/history side effects may not happen.

Two users update the same record:

- In most CRUD flows, last write wins. There is no broad optimistic concurrency guard.

A request is retried:

- Some flows are safe or deduped: Meta webhooks, public lead lookup, saved property toggle semantics, duplicate flags. Normal creates like tasks/deals/documents may duplicate if the client retries after a timeout.

## 20. System Mental Model

If you remember only 10 things about Nexora RealtyOS, remember these:

1. `Agency` is the tenant root. Almost every query and permission decision must start there.
2. `Property` is the supply-side core. It feeds public pages, marketing, leads, visits, deals, leases, documents, matching, reports, and saved searches.
3. `Lead` is the demand-side core. It gathers inquiries, messages, property interests, interactions, visits, deals, offers, docs, tasks, automation, and reports.
4. Public listing visibility is stricter than `is_published`: agency must be active/paid, listing must be publishable, freshness must exist, and expiry must be in the future.
5. The agency creates listings. Public users submit inquiries, reports, appointments, reviews, and other submissions; they do not self-publish properties in current behavior.
6. Verification is a checklist plus ordered milestone workflow; freshness is a separate availability workflow.
7. Lead automation is rule-based, not AI: rules, fallback, round robin, capacity, duplicate detection, SLA, escalation, and reassignment.
8. Meta inbox and property forms both become CRM activity, so lead workspace is the best mental hub for a buyer journey.
9. The scheduler is part of the product, not an optional helper. Without it, time-based trust and accountability features do not progress.
10. Stripe is platform subscription billing only; property transaction payments are not part of the current real estate flow.

## 21. Questions and Unknown Areas

Not determined from the provided code:

- Exact production deployment target and whether scheduler is separately monitored.
- Whether object storage, virus scanning, backups, or audit retention policies are configured outside this repo.
- Whether Meta webhook verification endpoint is correctly configured in production Meta app settings.
- Whether public customer tokens have planned expiry/rotation outside current code.
- Whether agency roles beyond the four hardcoded roles are planned.
- Whether property owner self-service submission will be added later; current code supports public valuation/submission flows, not direct owner-created listings.
- Whether property transaction accounting, rent collection, or escrow will be added later. Current recommendation is to keep property sale payments out of scope and consider small rent payments later, as already discussed.
