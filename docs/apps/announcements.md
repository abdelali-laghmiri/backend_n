# Announcements Module

## Purpose

The `announcements` module provides company-wide internal news and announcement records that:

- appear in the dashboard and a dedicated announcements page
- support `info`, `important`, and `mandatory` types
- support optional attachments
- track whether the current user has seen an announcement
- keep CRUD access permission-based

## Key Files

- `app/apps/announcements/models.py`
- `app/apps/announcements/schemas.py`
- `app/apps/announcements/service.py`
- `app/apps/announcements/router.py`
- `app/shared/uploads.py`
- `alembic/versions/b7c3d9e4f1a2_create_announcements_tables.py`

## Data Model

### `announcements`

- `id`
- `title`
- `summary`
- `content`
- `type`
- `is_pinned`
- `is_active`
- `published_at`
- `expires_at`
- `created_by_user_id`
- `updated_by_user_id`
- `created_at`
- `updated_at`

### `announcement_attachments`

- `id`
- `announcement_id`
- `original_file_name`
- `stored_file_name`
- `file_url`
- `content_type`
- `file_extension`
- `file_size_bytes`
- `uploaded_by_user_id`
- `created_at`

### `announcement_reads`

- `id`
- `announcement_id`
- `user_id`
- `seen_at`
- `created_at`

Constraint:

- one user can only have one read-tracking row per announcement via `uq_announcement_reads_announcement_user`

## Frontend Handoff

### Endpoint List

| Method | Path | Auth | Permission |
| --- | --- | --- | --- |
| `GET` | `/api/v1/announcements` | Bearer token required | `announcements.read` |
| `GET` | `/api/v1/announcements/{announcement_id}` | Bearer token required | `announcements.read` |
| `POST` | `/api/v1/announcements` | Bearer token required | `announcements.create` |
| `PUT` | `/api/v1/announcements/{announcement_id}` | Bearer token required | `announcements.update` |
| `DELETE` | `/api/v1/announcements/{announcement_id}` | Bearer token required | `announcements.delete` |
| `POST` | `/api/v1/announcements/{announcement_id}/mark-seen` | Bearer token required | `announcements.read` |
| `POST` | `/api/v1/announcements/{announcement_id}/attachments` | Bearer token required | `announcements.update` |
| `DELETE` | `/api/v1/announcements/{announcement_id}/attachments/{attachment_id}` | Bearer token required | `announcements.update` |

### List Query Parameters

`GET /api/v1/announcements`

- `limit`: optional integer, `1..100`
- `include_all`: optional boolean, default `false`

Behavior:

- normal frontend feed usage should call with default `include_all=false`
- `include_all=true` is only for management views and returns hidden items too
- if a read-only user calls `include_all=true`, the API returns `403`

### Create Payload

Content type: `application/json`

```json
{
  "title": "Q2 HR Policy Refresh",
  "summary": "Updated handbook sections are now available for all employees.",
  "content": "Full announcement body here.",
  "type": "important",
  "is_pinned": true,
  "is_active": true,
  "published_at": "2026-04-07T09:00:00Z",
  "expires_at": "2026-05-01T00:00:00Z"
}
```

### Update Payload

Content type: `application/json`

Important:

- `PUT` is implemented as a full update payload
- send the full announcement body again, not a partial patch
- attachments are managed through the dedicated attachment endpoints, not inside the `PUT` body

```json
{
  "title": "Q2 HR Policy Refresh",
  "summary": "Updated handbook sections and FAQs are now available for all employees.",
  "content": "Updated full announcement body here.",
  "type": "mandatory",
  "is_pinned": true,
  "is_active": true,
  "published_at": "2026-04-07T09:00:00Z",
  "expires_at": "2026-05-10T00:00:00Z"
}
```

### Attachment Upload Request

Content type: `multipart/form-data`

- field name: `files`
- repeat `files` for multiple uploads
- supported types: `pdf`, `doc`, `docx`, `xls`, `xlsx`, `ppt`, `pptx`, `csv`, `txt`, `jpg`, `jpeg`, `png`, `webp`, `gif`
- max file size: `10 MB` per file

### List Response Item

```json
{
  "id": 12,
  "title": "Q2 HR Policy Refresh",
  "summary": "Updated handbook sections are now available for all employees.",
  "type": "important",
  "is_pinned": true,
  "is_active": true,
  "is_currently_visible": true,
  "published_at": "2026-04-07T09:00:00Z",
  "expires_at": "2026-05-01T00:00:00Z",
  "is_seen": false,
  "seen_at": null,
  "has_attachments": true,
  "attachments_count": 2,
  "created_at": "2026-04-07T09:00:00Z",
  "updated_at": "2026-04-07T09:00:00Z",
  "created_by": {
    "id": 4,
    "matricule": "RH-001",
    "first_name": "Nadia",
    "last_name": "Amrani",
    "full_name": "Nadia Amrani"
  }
}
```

### Detail Response

```json
{
  "id": 12,
  "title": "Q2 HR Policy Refresh",
  "summary": "Updated handbook sections are now available for all employees.",
  "content": "Full announcement body here.",
  "type": "important",
  "is_pinned": true,
  "is_active": true,
  "is_currently_visible": true,
  "published_at": "2026-04-07T09:00:00Z",
  "expires_at": "2026-05-01T00:00:00Z",
  "is_seen": false,
  "seen_at": null,
  "has_attachments": true,
  "attachments_count": 2,
  "attachments": [
    {
      "id": 31,
      "file_name": "hr-policy-v2.pdf",
      "file_url": "/api/v1/announcements/12/attachments/31",
      "content_type": "application/pdf",
      "file_extension": ".pdf",
      "file_size_bytes": 248192,
      "created_at": "2026-04-07T09:00:05Z"
    },
    {
      "id": 32,
      "file_name": "faq.xlsx",
      "file_url": "/api/v1/announcements/12/attachments/32",
      "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "file_extension": ".xlsx",
      "file_size_bytes": 58121,
      "created_at": "2026-04-07T09:00:06Z"
    }
  ],
  "created_at": "2026-04-07T09:00:00Z",
  "updated_at": "2026-04-07T09:00:06Z",
  "created_by": {
    "id": 4,
    "matricule": "RH-001",
    "first_name": "Nadia",
    "last_name": "Amrani",
    "full_name": "Nadia Amrani"
  },
  "updated_by": {
    "id": 4,
    "matricule": "RH-001",
    "first_name": "Nadia",
    "last_name": "Amrani",
    "full_name": "Nadia Amrani"
  }
}
```

### Mark-Seen Response

```json
{
  "announcement_id": 12,
  "is_seen": true,
  "seen_at": "2026-04-07T09:02:10Z"
}
```

### Concrete List Response Example

```json
[
  {
    "id": 12,
    "title": "Q2 HR Policy Refresh",
    "summary": "Updated handbook sections are now available for all employees.",
    "type": "important",
    "is_pinned": true,
    "is_active": true,
    "is_currently_visible": true,
    "published_at": "2026-04-07T09:00:00Z",
    "expires_at": "2026-05-01T00:00:00Z",
    "is_seen": false,
    "seen_at": null,
    "has_attachments": true,
    "attachments_count": 2,
    "created_at": "2026-04-07T09:00:00Z",
    "updated_at": "2026-04-07T09:00:06Z",
    "created_by": {
      "id": 4,
      "matricule": "RH-001",
      "first_name": "Nadia",
      "last_name": "Amrani",
      "full_name": "Nadia Amrani"
    }
  },
  {
    "id": 15,
    "title": "Security Training Reminder",
    "summary": "Mandatory security refresher must be completed this week.",
    "type": "mandatory",
    "is_pinned": false,
    "is_active": true,
    "is_currently_visible": true,
    "published_at": "2026-04-06T13:00:00Z",
    "expires_at": null,
    "is_seen": true,
    "seen_at": "2026-04-06T15:30:00Z",
    "has_attachments": false,
    "attachments_count": 0,
    "created_at": "2026-04-06T13:00:00Z",
    "updated_at": "2026-04-06T13:00:00Z",
    "created_by": {
      "id": 6,
      "matricule": "DM-003",
      "first_name": "Yassine",
      "last_name": "Bennani",
      "full_name": "Yassine Bennani"
    }
  }
]
```

### Frontend Integration Notes

#### Dashboard Cards

Use these fields for dashboard cards or homepage highlights:

- `id`
- `title`
- `summary`
- `type`
- `is_pinned`
- `published_at`
- `expires_at`
- `is_seen`
- `has_attachments`
- `attachments_count`

Recommended dashboard call:

- `GET /api/v1/announcements?limit=5`

Because ordering is pinned-first, the first items are already the best candidates for highlights.

#### Announcement Detail Page

Use these fields for the full page:

- `title`
- `summary`
- `content`
- `type`
- `published_at`
- `expires_at`
- `attachments`
- `created_by`
- `updated_by`
- `is_seen`
- `seen_at`

#### Type Display Rules

- `info`: normal informational styling
- `important`: stronger visual emphasis than `info`
- `mandatory`: highest priority styling and the strongest callout

The backend ordering priority is:

1. `is_pinned=true`
2. `mandatory`
3. `important`
4. `info`
5. newest `published_at`

#### Seen State

- `is_seen=false` means the current authenticated user has no read-tracking row yet
- `is_seen=true` means the current user already triggered `mark-seen`
- `seen_at` is the timestamp of that first seen event
- `mark-seen` is idempotent, so the frontend can safely call it multiple times without creating duplicates

Recommended frontend behavior:

- fetch detail page first
- once the detail page is actually opened or considered viewed, call `POST /api/v1/announcements/{id}/mark-seen`
- update local UI state from the mark-seen response

#### Slider / Highlight Section

Safe fields for a slider or top-banner section:

- `id`
- `title`
- `summary`
- `type`
- `is_pinned`
- `published_at`
- `has_attachments`

Do not assume:

- there will always be pinned items
- there will always be a mandatory item
- attachments will always be images

#### Attachment Rendering Notes

- `attachments` only appear in detail responses
- each attachment contains `file_url`, `content_type`, and `file_extension`
- use `file_extension` or `content_type` to choose icons
- `file_url` is an authenticated backend route that validates announcement read access before serving the file
- the frontend should open `file_url` with the same authenticated session used for announcement API calls

### Permission Codes

New permission codes introduced by this feature:

- `announcements.read`
- `announcements.create`
- `announcements.update`
- `announcements.delete`

Read permission:

- `announcements.read`

Write permissions:

- `announcements.create`
- `announcements.update`
- `announcements.delete`

Default setup-role seeding in this repository:

- `RH_MANAGER`: read + create + update + delete
- `DEPARTMENT_MANAGER`: read + create + update + delete
- `TEAM_LEADER`: read only
- `EMPLOYEE`: read only

### Assumptions And Limitations

- V1 is company-wide only. There is no team, department, or audience targeting yet.
- There are no comments, reactions, acknowledgements, analytics, or realtime push updates.
- `DELETE` is implemented as soft delete by setting `is_active=false`.
- The public feed never returns inactive, unpublished, or expired announcements unless a management user explicitly calls `include_all=true`.
- `PUT` is a full update body, not a partial patch.
- Attachments are managed in separate endpoints, not inline inside the create or update JSON payload.
- Attachment files are served through an authenticated announcement route. The frontend should not assume public static URLs, signed URLs, or object storage semantics.
