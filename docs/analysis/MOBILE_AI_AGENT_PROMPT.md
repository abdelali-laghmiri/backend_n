# AI Agent Prompt - Build Mobile MVP (Login, Demandes, Announcements, Messages)

Use this exact prompt with an AI coding agent.

---

You are a senior mobile engineer. Build a production-ready MVP mobile app connected to my backend API.

## 1) Goal

Build a small mobile app focused only on:

1. Login
2. Create demande (request)
3. List my demandes
4. See announcements
5. Create/send message
6. Logout

Do not build extra modules.

## 2) Backend context

- Backend base URL: `https://backend-n-lac.vercel.app`
- API prefix: `/api/v1`
- Auth type: Bearer JWT
- Header format: `Authorization: Bearer <access_token>`

## 3) Required API endpoints

### Auth

- `POST /api/v1/auth/login`
  - body:
    ```json
    {
      "matricule": "EMP-0001",
      "password": "YourPassword123!",
      "issue_refresh_token": true,
      "device_id": "mobile-device-001"or "adresss mac of devise" 
    }
    ```
  - save `access_token`, `expires_in`, optional `refresh_token`

- `GET /api/v1/auth/me`
  - use to load current user profile and permissions after login

Notes:

- If `must_change_password=true`, show blocking UI notice.
- There is no public API logout endpoint, so logout = clear local tokens/session.

### Requests (Demandes)

- `GET /api/v1/requests/types`
- `GET /api/v1/requests/types/{request_type_id}/fields`
- `POST /api/v1/requests`
  - body:
    ```json
    {
      "request_type_id": 1,
      "values": {
        "start_date": "2026-05-10",
        "end_date": "2026-05-12",
        "reason": "Family event"
      }
    }
    ```
- `GET /api/v1/requests`

### Announcements

- `GET /api/v1/announcements`
- `GET /api/v1/announcements/{announcement_id}`

### Messages

- `GET /api/v1/messages/users?q=<query>&limit=100`
- `POST /api/v1/messages`
  - body:
    ```json
    {
      "subject": "Demande de conge",
      "body": "Bonjour, ma demande est soumise.",
      "recipients": [
        {
          "user_id": 12,
          "can_reply": true
        }
      ]
    }
    ```
- Optional (nice to have):
  - `GET /api/v1/messages/inbox`
  - `GET /api/v1/messages/sent`
  - `GET /api/v1/messages/unread-count`

## 4) Permissions expected from backend user

The authenticated user should have:

- `requests.create`
- `requests.read`
- `announcements.read`
- `messages.read`
- `messages.read_users`
- one of:
  - `messages.send_all`
  - `messages.send_same_or_down`
  - `messages.send`

If a permission is missing, show a clear UI error state.

## 5) Tech stack requirements

Pick one and continue fully (do not ask me):

- Preferred: React Native + Expo + TypeScript
- State: Zustand or Redux Toolkit
- Networking: Axios with interceptors
- Forms: React Hook Form + Zod
- Storage: secure token storage (Expo SecureStore / platform secure storage)
- Navigation: React Navigation

## 6) App screens (exact MVP)

1. `LoginScreen`
   - matricule, password
   - login button
   - error messages

2. `HomeScreen`
   - quick cards to navigate
   - announcements preview

3. `CreateDemandeScreen`
   - load request types
   - load dynamic fields based on selected type
   - submit request

4. `MyDemandesScreen`
   - list current user requests
   - show status, type, created date

5. `AnnouncementsScreen`
   - list announcements
   - open announcement details

6. `CreateMessageScreen`
   - search recipients
   - select recipient(s)
   - subject/body
   - send message

7. `SettingsScreen`
   - logout (clear tokens + reset nav)

## 7) Architecture and code quality rules

- Use feature-based folders.
- Create a typed API client module.
- Centralize endpoint paths/constants.
- Handle loading/error/empty states on every screen.
- Add request timeout and friendly retry.
- Never hardcode tokens in code.
- Keep all code in TypeScript.

## 8) Auth/session behavior

- On app start:
  - if token exists -> call `/auth/me`
  - if success -> enter app
  - else -> clear session and go login
- Logout:
  - clear secure storage + in-memory state
  - navigate to login

## 9) API error handling

- `401`: session expired -> force relogin
- `403`: show permission denied message
- `404`: show not found state
- `409`: show conflict alert
- `422/400`: show validation errors near fields when possible

## 10) What to deliver

Deliver all of the following in one response:

1. Project structure tree
2. Full source code for key files
3. `.env.example` for mobile app API URL
4. Steps to run locally
5. Test checklist for all 6 core features
6. Known limitations and next improvements

## 11) Acceptance criteria

MVP is accepted only if:

- I can login with valid backend credentials.
- I can create a demande and see it in my demandes list.
- I can list and open announcements.
- I can send a message to a valid recipient.
- Logout fully clears session and returns to login.

Now implement the complete app.

---

If needed, replace `http://<MY_BACKEND_HOST>:8000` with your real backend host before using this prompt.
