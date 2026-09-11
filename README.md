# Creator Publishing App

A reliable, scalable creator-publishing platform for preparing, scheduling, publishing, and monitoring image and video content across eight social-media platforms through one unified dashboard.

The system is designed around a simple workflow:

```text
Connect → Create → Validate → Preview → Schedule or Publish → Verify → Notify → Review
```

Its main design principle is safety: the app must never claim that content was published when the result is uncertain, and it must never blindly retry an ambiguous publishing request.

---

## Table of Contents

- [Overview](#overview)
- [Goals](#goals)
- [Core Features](#core-features)
- [User Workflows](#user-workflows)
- [Unified Dashboard](#unified-dashboard)
- [Platform Integrations](#platform-integrations)
- [Content Creation](#content-creation)
- [Validation and Preview](#validation-and-preview)
- [Scheduling and Time Zones](#scheduling-and-time-zones)
- [Publishing Reliability](#publishing-reliability)
- [Notifications and Errors](#notifications-and-errors)
- [Content Library and Calendar](#content-library-and-calendar)
- [Analytics](#analytics)
- [Onboarding and Demo Workspace](#onboarding-and-demo-workspace)
- [Localization](#localization)
- [Help and Feedback](#help-and-feedback)
- [Administration](#administration)
- [Security and Privacy](#security-and-privacy)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Data Model](#data-model)
- [MVP Scope](#mvp-scope)
- [Testing](#testing)
- [Development Principles](#development-principles)
- [Future Enhancements](#future-enhancements)

---

## Overview

The Creator Publishing App gives creators one place to manage social-media publishing without requiring them to repeat the same work on every platform.

Users can:

- Connect supported social-media accounts.
- Upload images and videos.
- Create shared or platform-specific captions.
- Preview content before publishing.
- Validate content against platform requirements.
- Publish immediately.
- Schedule posts for later.
- Monitor publishing status.
- Handle errors safely.
- Review basic analytics.
- Download media and copy captions for manual publishing when required.

The application must use official APIs and OAuth integrations whenever available. Platform capabilities must be configurable because different platforms support different media types, limits, publishing methods, scheduling options, permissions, and analytics.

---

## Goals

### Primary goals

1. Make cross-platform publishing simple.
2. Prevent duplicate or falsely reported posts.
3. Clearly communicate platform limitations.
4. Support both beginners and experienced creators.
5. Provide a flexible architecture for adding platforms and features.
6. Keep customers and administrators in one shared dashboard.
7. Provide reliable scheduling through background jobs.
8. Make errors understandable and actionable.

### Non-goals for the initial version

The first release does not need to be a complete video editor, AI content studio, billing platform, or advanced enterprise collaboration system. Those capabilities should be possible later without changing the core publishing architecture.

---

## Core Features

### Authentication

- Email registration.
- Login and logout.
- Password reset.
- Email verification.
- Secure sessions.
- Optional social login.
- Account deletion.
- User data export.
- Secure OAuth connection to external platforms.

### Creator workspace

- Unified dashboard.
- Content creation workflow.
- Content library.
- Calendar.
- Platform connections.
- Notifications.
- Analytics.
- Help center.
- Feedback area.
- User settings.

### Publishing

- Immediate publishing.
- Future scheduling.
- Draft saving.
- Platform-specific captions.
- Platform-specific previews.
- Validation before publishing.
- Publishing verification.
- Safe retry policy.
- Manual fallback tools.

### Administration

- Role-based access control.
- User management.
- Publishing-job monitoring.
- Platform-health monitoring.
- Support management.
- Feedback management.
- Moderation tools.
- Audit logs.
- Feature flags and system settings.

---

## User Workflows

### New-user workflow

```text
Register
→ Verify email
→ Complete or skip onboarding
→ Enter dashboard
→ Connect a platform
→ Create or upload content
```

### Publishing workflow

```text
Create content
→ Select platforms
→ Apply platform-specific settings
→ Validate media and captions
→ Review previews and warnings
→ Confirm
→ Publish or schedule
→ Verify result
→ Notify user
```

### Failure workflow

```text
Publishing attempt
→ Receive response
→ Verify using platform ID or status endpoint
→ Mark Published, Failed, or Status Unknown
→ Notify user
→ Retry only when safe
```

### Scheduled publishing workflow

```text
User schedules content
→ Store scheduled time in UTC
→ Create background job
→ Worker starts at the required time
→ Platform adapter publishes content
→ Verification service checks result
→ Notification is sent
```

---

## Unified Dashboard

Customers and administrators use the same dashboard shell. There must not be separate customer and administrator dashboard applications.

### Main routes

```text
/dashboard
/dashboard/create
/dashboard/content
/dashboard/calendar
/dashboard/analytics
/dashboard/platforms
/dashboard/notifications
/dashboard/help
/dashboard/feedback
/dashboard/settings
/dashboard/administration
```

### Shared dashboard features

- Shared header.
- Shared sidebar.
- Shared breadcrumbs.
- Responsive mobile navigation.
- User profile menu.
- Notification access.
- Role-aware navigation.
- Permission-based route protection.
- Shared design system.

### Customer dashboard cards

- Draft content.
- Upcoming scheduled posts.
- Recently published content.
- Failed posts.
- Posts requiring review.
- Platform connection status.
- Basic analytics.
- Recommended next actions.

### Administrator dashboard cards

Administrators see the normal creator dashboard plus cards permitted by their roles:

- Platform health.
- Failed publishing jobs.
- Open support tickets.
- New feedback.
- System warnings.
- Active-user summaries.

Administration features must be hidden from unauthorized users and protected by server-side permission checks.

---

## Platform Integrations

The system is designed to support eight social-media platforms. Until final platform names and APIs are confirmed, integrations should be represented as configurable adapters such as `platform-1` through `platform-8`.

Each platform adapter must manage:

- OAuth authorization.
- Token refresh.
- Account information.
- Connection health.
- Platform capabilities.
- Content validation.
- Media upload.
- Publishing.
- Publishing verification.
- Analytics retrieval.
- Platform-specific errors.

### Capability matrix

Each platform must declare capabilities such as:

```text
canPublish
canSchedule
canUploadVideo
canUploadImage
canSetThumbnail
canSetAltText
canSetVisibility
canReadAnalytics
supportsCaptionEditing
maximumFileSize
supportedFormats
maximumDuration
maximumCaptionLength
```

The interface must use this matrix to:

- Hide unsupported controls.
- Explain unavailable features.
- Block known-invalid publishing attempts.
- Show warnings before confirmation.
- Distinguish unsupported features from temporary failures.

The app must not imply that every platform has identical functionality.

---

## Content Creation

Users can create a content item by uploading a finished image or video or by starting with an idea and entering content manually.

### Supported content fields

- Media file.
- Media type.
- Title where supported.
- Caption.
- Hashtags.
- Thumbnail where supported.
- Alt text where supported.
- Platform selection.
- Visibility where supported.
- Scheduled time.
- Draft status.

### Platform-specific content

A single content item can contain separate platform configurations:

```text
Platform caption
Platform title
Platform hashtags
Platform thumbnail
Platform alt text
Platform visibility
Platform scheduled time
```

Users can either reuse one shared caption or edit each platform version separately.

The app must never silently truncate, remove, translate, or alter content. Any required adaptation must be shown to the user for approval.

### Optional future AI features

- Caption suggestions.
- Hashtag suggestions.
- Content ideas.
- Tone adjustment.
- Platform-specific rewriting.
- Translation.

AI output must be optional, clearly labeled, editable, and approved before publishing.

### MVP limitation

A built-in video editor is not required for the first release. Users can upload finished media created in another application.

---

## Validation and Preview

### Validation

Before scheduling or publishing, validate:

- File type.
- File size.
- Video duration.
- Aspect ratio.
- Resolution.
- Caption length.
- Hashtag limits.
- Required fields.
- Thumbnail rules.
- Audio restrictions where applicable.
- Platform permissions.
- Account connection status.
- Scheduling support.
- Scheduled time.

Validation results are divided into:

- **Errors:** publishing is blocked.
- **Warnings:** publishing may continue after review.
- **Information:** no action is required.

### Preview

The platform-specific preview displays:

- Media.
- Caption.
- Title.
- Hashtags.
- Thumbnail.
- Approximate platform layout.
- Destination platform.
- Publish or scheduled time.
- Warnings.
- Unsupported features.

Use visible labels such as:

```text
Ready to publish
Needs attention
Unsupported feature
Requires platform permission
Preview approximation
```

The preview is an approximation and must not be presented as a guarantee of identical rendering on the destination platform.

---

## Scheduling and Time Zones

Users can:

- Publish immediately.
- Schedule posts.
- Edit scheduled posts.
- Cancel scheduled posts.
- Reschedule scheduled posts.
- Duplicate scheduled posts.
- Save drafts.

### Time-zone requirements

- Store scheduled timestamps internally in UTC.
- Display the user’s selected time zone.
- Display the destination platform’s time zone.
- Apply daylight-saving rules.
- Allow manual time-zone override.
- Warn the user when time zones differ.
- Prevent accidental scheduling in the past.
- Use the platform’s actual account time zone when available.

The confirmation screen must show the exact intended publishing time in both relevant time zones.

---

## Publishing Reliability

Reliability is a core product feature.

### Required rules

1. Never treat a timeout or ambiguous response as a confirmed failure.
2. Verify results using a platform post ID or status endpoint whenever possible.
3. If verification is unavailable, mark the result `STATUS_UNKNOWN`.
4. Never automatically retry an unknown result.
5. Automatically retry only once for a confirmed temporary technical failure.
6. Never automatically retry authentication failures.
7. Never automatically retry invalid content.
8. Never automatically retry permission failures.
9. Never retry if the platform may already have published the content.
10. Require user review for further retries.
11. Generate an idempotency key for every publishing attempt.
12. Store each attempt and response.
13. Display the final status clearly to the user.
14. Provide a download and copy fallback.

### Publishing statuses

```text
DRAFT
SCHEDULED
PUBLISHING
PUBLISHED
FAILED
STATUS_UNKNOWN
CANCELLED
REQUIRES_AUTHENTICATION
REQUIRES_USER_REVIEW
```

### Allowed state transitions

```text
DRAFT → SCHEDULED
DRAFT → PUBLISHING
SCHEDULED → PUBLISHING
SCHEDULED → CANCELLED
PUBLISHING → PUBLISHED
PUBLISHING → FAILED
PUBLISHING → STATUS_UNKNOWN
PUBLISHING → REQUIRES_AUTHENTICATION
FAILED → PUBLISHING
STATUS_UNKNOWN → REQUIRES_USER_REVIEW
REQUIRES_USER_REVIEW → PUBLISHING
REQUIRES_USER_REVIEW → CANCELLED
```

Invalid transitions such as `PUBLISHED → PUBLISHING` must be rejected by a centralized state machine.

The two transitions leaving `REQUIRES_USER_REVIEW` are user-initiated only — they are the manual
retry described under "Failure workflow" and the user abandoning the post. Neither may be reached
from a background job, because an automatic retry from review reintroduces the duplicate-post hazard
rule 9 forbids. The state machine cannot enforce that; it is the caller's obligation, discharged by
the permission check and audit write on the API route.

---

## Notifications and Errors

Notify users when:

- A post is published.
- A scheduled post fails.
- A post has unknown status.
- A connection expires.
- A platform disconnects.
- Content requires review.
- A scheduled time changes.
- Analytics are updated.
- A support request receives a response.

### Error messages

Errors must explain:

- What happened.
- Which platform was affected.
- Whether the post might already exist.
- Whether retrying is safe.
- What the user should do next.

Example:

```text
Publishing could not be confirmed. The platform may have received the post. Do not retry until you check the destination account.
```

The app must not expose raw API errors without a clear user-facing explanation.

### Manual fallback

When publishing is unavailable or unsafe, the user can:

- Download the media.
- Copy the caption.
- Copy hashtags.
- View platform-specific instructions.
- Open the platform manually where possible.

---

## Content Library and Calendar

### Content library

Support:

- Drafts.
- Scheduled content.
- Published content.
- Failed content.
- Unknown-status content.
- Search.
- Filtering by date, platform, status, and content type.
- Sorting.
- Duplication.
- Archiving.
- Media download.
- Caption copying.

Permanent deletion must require explicit confirmation.

### Calendar

Support:

- Month view.
- Week view.
- List view.
- Platform filters.
- Status indicators.
- Time-zone display.
- Opening a post from the calendar.
- Editing scheduled content.
- Cancelling scheduled posts.
- Rescheduling scheduled posts.
- Duplicating posts.

Published content must not be editable unless the destination platform supports editing.

---

## Analytics

Where supported by official platform APIs, show:

- Views.
- Likes.
- Comments.
- Shares.
- Saves.
- Clicks.
- Engagement rate when reliably calculated.

Every metric must show:

- Source platform.
- Measurement period.
- Last updated time.
- Metric definition.
- Whether it is direct or estimated.
- Whether it is unavailable.

Metrics must not be compared across platforms as though the definitions are identical.

The MVP may provide per-platform analytics instead of advanced cross-platform comparisons.

---

## Onboarding and Demo Workspace

### Onboarding

Onboarding is guided but skippable.

Collect:

- Display name.
- Creator or brand name.
- Audience.
- Niche.
- Tone.
- Goals.
- Preferred platforms.
- Language.
- Time zone.
- Notification preferences.
- Optional brand details.

Users can edit these settings later.

### Demo workspace

The optional demo workspace includes:

- Example content ideas.
- Sample image and video posts.
- Example captions.
- Sample schedules.
- Preview examples.
- Sample analytics.
- Sample notifications.

All demo records must include `is_demo = true` and must be impossible to publish to real platforms.

---

## Localization

The application must be internationalization-ready from the beginning.

Support:

- User-selected language.
- Localized interface text.
- Local date formats.
- Local time formats.
- Time-zone selection.
- Currency and number formatting.
- Right-to-left layouts.
- Localized notifications.
- Localized help content.
- Localized validation messages.

Do not hardcode visible text.

Machine-translated captions must be labeled and editable. Culturally sensitive or uncertain wording should be flagged for review.

---

## Help and Feedback

### Help center

Provide a searchable help center with:

- Setup guides.
- Platform connection guides.
- Publishing instructions.
- Scheduling instructions.
- Troubleshooting.
- Frequently asked questions.
- Short tutorials.
- Contextual help links.
- Contact-support option.

### Feedback system

Users can:

- Submit feature requests.
- Report bugs.
- Upload screenshots or videos.
- Rate their experience.
- Vote on proposed improvements.
- Track submissions.
- Receive status updates.

Feedback statuses:

```text
RECEIVED
UNDER_REVIEW
PLANNED
IN_PROGRESS
COMPLETED
DECLINED
```

Private user data must not be exposed in public feedback areas.

---

## Administration

Administration is located inside the shared dashboard at:

```text
/dashboard/administration
```

### Administration capabilities

- User management.
- Role and permission management.
- Platform connection monitoring.
- Platform health.
- Publishing-job monitoring.
- Failed-job management.
- Support tickets.
- Feedback management.
- Moderation.
- Feature flags.
- System settings.
- Help-center management.
- Audit logs.

### Roles

Possible roles include:

```text
customer
support_agent
moderator
finance_admin
technical_admin
owner
```

Use permissions instead of hardcoding behavior around role names.

Example permissions:

```text
content.create
content.update
content.delete
content.publish
analytics.view
platforms.connect
feedback.submit
admin.dashboard.view
admin.users.view
admin.users.manage
admin.publishing.view
admin.platforms.manage
admin.support.manage
admin.moderation.manage
admin.audit_logs.view
```

### Audit logs

Log sensitive actions with:

```text
actor
action
resource type
resource ID
previous state
new state
timestamp
```

Administrator routes must be protected on the server. Hiding navigation links alone is not security.

---

## Security and Privacy

Implement:

- Secure password hashing.
- Encrypted platform access and refresh tokens.
- OAuth authentication.
- Token refresh.
- Session expiry.
- Role-based access control.
- Server-side permission checks.
- Input validation.
- Rate limiting.
- CSRF protection.
- Secure file access.
- Audit logging.
- Data export.
- Account deletion.
- Consent controls.
- Minimal external API permissions.
- Safe error handling.

Never store external platform passwords.

Never expose access tokens to the browser or logs.

---

## Architecture

Use the following responsibility boundaries:

- Pages handle routing and layout.
- Features handle user-facing behavior.
- Packages contain reusable business logic.
- Platform adapters contain platform-specific behavior.
- Services coordinate business workflows.
- Repositories handle database access.
- Workers handle scheduled and long-running jobs.
- Permissions protect actions and routes.
- Notifications communicate system events.

### Platform adapter interface

```ts
interface PlatformAdapter {
  getCapabilities(): PlatformCapabilities;
  connect(input: ConnectInput): Promise<ConnectionResult>;
  refreshConnection(input: RefreshInput): Promise<ConnectionResult>;
  validatePost(input: ValidatePostInput): Promise<ValidationResult>;
  publishPost(input: PublishPostInput): Promise<PublishResult>;
  verifyPost(input: VerifyPostInput): Promise<VerificationResult>;
  getAnalytics(input: AnalyticsInput): Promise<AnalyticsResult>;
}
```

### Shared services

Important shared services include:

- `publishing-service`
- `verification-service`
- `retry-policy`
- `idempotency-service`
- `notification-service`
- `media-validation-service`
- `scheduling-service`
- `permission-service`
- `analytics-service`

Complex business logic must not be placed directly in buttons, pages, or route handlers.

---

## Project Structure

```text
apps/
├── web/
│   ├── app/
│   │   ├── (marketing)/
│   │   ├── (auth)/
│   │   └── dashboard/
│   │       ├── layout.tsx
│   │       ├── page.tsx
│   │       ├── create/
│   │       ├── content/
│   │       ├── calendar/
│   │       ├── analytics/
│   │       ├── platforms/
│   │       ├── notifications/
│   │       ├── help/
│   │       ├── feedback/
│   │       ├── settings/
│   │       └── administration/
│   ├── components/
│   ├── features/
│   ├── hooks/
│   ├── lib/
│   ├── styles/
│   ├── types/
│   └── middleware.ts
│
└── worker/
    └── src/
        ├── jobs/
        ├── queues/
        ├── schedulers/
        └── index.ts

packages/
├── database/
├── platform-adapters/
├── publishing/
├── validation/
├── auth/
├── permissions/
├── storage/
├── analytics/
├── notifications/
├── localization/
├── help-center/
├── feedback/
├── audit/
├── config/
├── logger/
├── shared-types/
└── ui/
```

Do not create a large generic `utils` folder. Use descriptive, responsibility-based files.

---

## Data Model

### User

```text
id
email
display_name
preferred_language
time_zone
notification_preferences
onboarding_status
created_at
updated_at
```

### Brand profile

```text
id
user_id
brand_name
tone
audience
goals
logo
brand_colors
default_hashtags
```

### Platform connection

```text
id
user_id
platform
account_id
account_name
encrypted_access_token
encrypted_refresh_token
permissions
capabilities
connection_status
last_verified_at
created_at
updated_at
```

### Content item

```text
id
user_id
title
media_url
media_type
caption
is_demo
status
created_at
updated_at
```

### Platform post

```text
id
content_item_id
platform
platform_caption
platform_title
platform_thumbnail
platform_alt_text
scheduled_at_utc
platform_time_zone
status
platform_post_id
idempotency_key
attempt_count
last_error
published_at
verified_at
created_at
updated_at
```

### Publishing attempt

```text
id
platform_post_id
attempt_number
request_started_at
request_finished_at
response_code
response_payload
platform_post_id
result
error_type
error_message
created_at
```

### Notification

```text
id
user_id
type
title
message
related_content_id
read_at
created_at
```

### Feedback

```text
id
user_id
type
title
description
attachments
status
votes
created_at
updated_at
```

### Audit log

```text
id
actor_id
action
resource_type
resource_id
previous_state
new_state
created_at
```

---

## MVP Scope

The initial release should prioritize a reliable publishing workflow.

### Include in MVP

- Registration and login.
- Optional onboarding.
- Shared customer and administrator dashboard.
- One or two platform integrations initially.
- Image and video upload.
- Caption entry.
- Basic platform validation.
- Platform preview.
- Immediate publishing.
- Simple scheduling.
- Calendar.
- Drafts.
- Publishing verification.
- Safe error handling.
- Notifications.
- Download and copy fallback.
- Basic administration.
- Basic help content.
- Platform capability system.
- Background worker.

### Defer until later

- Built-in video editor.
- Advanced AI generation.
- Automatic translation.
- Advanced cross-platform analytics.
- Complex team approval workflows.
- Full subscription billing.
- Advanced content recommendations.
- All eight platform integrations at launch.
- Extensive administrator role types.

The architecture must allow deferred features to be added later without rewriting the publishing system.

---

## Testing

### Unit tests

Test:

- Media validation.
- Caption validation.
- Platform capabilities.
- Time-zone conversion.
- Publishing-state transitions.
- Retry decisions.
- Permission checks.
- Idempotency behavior.
- Notification rules.

### Integration tests

Test:

- Platform connection.
- OAuth callback.
- Token refresh.
- Content creation.
- Scheduling.
- Publishing.
- Publishing verification.
- Expired authentication.
- Unknown publishing status.
- Notification delivery.

### End-to-end tests

Test the successful flow:

```text
Register
→ connect platform
→ upload content
→ validate
→ preview
→ schedule
→ worker publishes
→ verify result
→ notify user
```

Test failure flows:

```text
Timeout
→ status unknown
→ no automatic retry
→ user review required
```

```text
Temporary technical error
→ one safe retry
→ verification
```

```text
Expired token
→ notification
→ reconnect
→ review before retry
```

```text
Unsupported format
→ publishing blocked
→ correction instructions
```

---

## Development Principles

1. Keep the core workflow simple.
2. Keep platform-specific behavior inside adapters.
3. Centralize publishing status transitions.
4. Centralize retry rules.
5. Never guess whether publishing succeeded.
6. Never blindly retry ambiguous responses.
7. Keep database access outside UI components.
8. Use background workers for scheduled operations.
9. Use permissions for administration.
10. Keep customers and administrators in the same dashboard.
11. Make platform capabilities configurable.
12. Keep demo data separate from real data.
13. Do not silently modify user content.
14. Clearly explain unsupported features.
15. Test failures as carefully as successes.
16. Prefer a smaller reliable MVP to a large fragile product.
17. Keep the codebase understandable through descriptive names and clear boundaries.
18. Add new platforms through adapters rather than scattered application changes.

---

## Future Enhancements

Potential future features include:

- All eight platform integrations.
- AI caption generation.
- AI content ideas.
- AI hashtag suggestions.
- Automatic translation.
- Built-in video editing.
- Brand kits.
- Team workspaces.
- Approval workflows.
- Advanced analytics.
- Content recommendations.
- Subscription plans.
- Billing and invoices.
- Mobile applications.
- Browser extension.
- More notification channels.
- Advanced moderation.
- Public feedback roadmap.

These features should be added only after the core publishing workflow is reliable.

---

## Completion Criteria

The system is ready for its initial release when:

1. A user can register and access one shared dashboard.
2. A user can skip onboarding and still use the app.
3. A user can connect a supported platform.
4. A user can upload an image or video.
5. A user can add and edit captions.
6. The system validates known platform restrictions.
7. The system displays platform limitations clearly.
8. A user can preview content before publishing.
9. A user can publish immediately.
10. A user can schedule content.
11. Scheduled publishing works without the browser remaining open.
12. Publishing status is verified whenever possible.
13. Ambiguous results become `STATUS_UNKNOWN`.
14. Unknown results are never automatically retried.
15. Temporary failures receive no more than one automatic retry.
16. Authentication failures require reconnection.
17. Failed posts provide useful instructions.
18. Users can download media and copy captions.
19. Time zones are handled correctly.
20. Demo content cannot be published accidentally.
21. Administrators use the same dashboard shell as customers.
22. Administration features are permission-protected.
23. Sensitive administrator actions are audit logged.
24. The interface is responsive and accessible.
25. New platforms can be added through adapters.
26. The main workflow remains understandable.

---

## Final Product Principle

> Make publishing simple for the user, but make the system cautious whenever the publishing result is uncertain.
