# Notifications Module

## Purpose

The `notifications` module provides:

- persisted notification records
- unread-count queries
- mark-read actions
- websocket push for realtime delivery

## Key Files

- `app/apps/notifications/models.py`
- `app/apps/notifications/schemas.py`
- `app/apps/notifications/service.py`
- `app/apps/notifications/router.py`
- `app/apps/notifications/realtime.py`

## Main Interfaces

- list notifications
- unread count
- mark one as read
- mark all as read
- websocket endpoint for realtime updates

## How It Works

### Persistence

Notifications are stored in the `notifications` table so users can retrieve them later even if a websocket session was not connected.

### Realtime Delivery

The connection manager tracks active websocket connections per user ID in memory. When a new notification is created, the service can trigger a publish to the active connections for that user.

### Authentication

The websocket endpoint authenticates by extracting a token from either:

- the `token` query parameter
- the `Authorization: Bearer ...` header

## Dependencies

- `auth` service for token validation
- any business module that creates notifications, especially `requests`

## Inputs and Outputs

### Inputs

- authenticated user context
- notification creation payloads from other services
- websocket access token

### Outputs

- notification lists and unread counts
- realtime JSON payloads delivered to websocket clients

## Important Logic

- REST endpoints are user-scoped; users only operate on their own notifications.
- The realtime manager removes stale websocket connections when sends fail.
- Synchronous service code can trigger async websocket publishes through a thread-safe scheduler helper.

## Issues Found

- Confirmed: websocket connections are stored only in process memory, so realtime delivery will not coordinate across multiple application instances.
- Confirmed: websocket auth supports `token` as a query parameter, which increases the chance of token leakage through logs, browser history, or intermediaries.
- Confirmed: websocket send scheduling uses `asyncio.create_task` on the current process event loop, which reinforces the single-process design assumption.

## Recommendations

- Move realtime fan-out to a shared broker or explicitly document single-instance expectations.
- Prefer authorization headers over query-string tokens for websocket authentication where possible.
- Add delivery and reconnect behavior tests if notifications are important to operational workflows.
