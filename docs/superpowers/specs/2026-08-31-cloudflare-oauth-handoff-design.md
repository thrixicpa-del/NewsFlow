# Cloudflare OAuth handoff for YouTube channels

## Goal

Replace the desktop loopback callback as NewsFlow's primary YouTube OAuth
completion path. Google returns to an HTTPS endpoint at
`https://a.tinkbro.online/oauth/youtube/callback`; a dedicated Cloudflare
Worker transfers the resulting credentials to the waiting NewsFlow desktop
instance through a one-time, short-lived session.

The existing one-Chrome-profile-per-channel model remains unchanged. Each
channel keeps its own Google login and its own DPAPI-protected refresh token
on the local Windows account.

## Non-goals

- Do not store channel refresh tokens permanently in Cloudflare.
- Do not use the everyday Chrome profile for channel OAuth.
- Do not publish or change any YouTube video while validating the flow.
- Do not expose an OAuth client secret or a refresh token to the NewsFlow UI,
  logs, screenshots, or support messages.

## OAuth topology

Google OAuth requires a new client of type **Web application** in the existing
Google Cloud project. Its only authorized redirect URI is:

`https://a.tinkbro.online/oauth/youtube/callback`

NewsFlow uses the Web client ID and the Cloudflare service base URL. The Web
client secret is stored only as a Cloudflare Worker secret. The Worker performs
the authorization-code exchange over HTTPS.

```text
NewsFlow + channel Chrome profile
  -> Worker: create one-time session
  -> Google consent page
  -> Worker callback: exchange code
  -> Worker: encrypted, short-lived result
  -> NewsFlow: poll once and store token with Windows DPAPI
  -> Worker: delete session
```

## Worker contract

The Worker exposes three HTTPS endpoints under `/oauth/youtube/`:

1. `POST /sessions`
   - Creates a random opaque session ID and a distinct poll capability.
   - Accepts only the client-provided public channel profile ID as local
     correlation metadata; it never receives a channel name or token.
   - Persists a pending record for ten minutes.

2. `GET /callback`
   - Verifies the opaque state and session expiry.
   - Exchanges the Google authorization code with the Worker-held Web client
     secret.
   - Stores the token payload only in the temporary session, encrypted at rest
     with a Worker secret-derived key, and renders a simple success page.

3. `POST /sessions/:id/consume`
   - Requires the poll capability.
   - Returns the payload once, marks it consumed, and deletes the session.
   - Returns explicit `pending`, `denied`, `expired`, and `consumed` states
     without token material in error messages.

Session records use a Cloudflare D1 database so creation, transition to ready,
and one-time consumption are transactional. A scheduled cleanup removes
expired records; every request also rejects expired records immediately.

## Desktop contract

`scriptor/youtube_oauth.py` gains a callback-client flow that:

- creates a pending Worker session;
- opens the Google authorization URL in the selected channel profile and a new
  Chrome window;
- polls only the corresponding session until completion or expiry;
- validates the returned credential and fetches the actual YouTube channel;
- persists the refreshed token in the existing `youtube_oauth_tokens` mapping.

The mapping is already encrypted by Windows DPAPI when `settings.json` is
written. The UI receives only public channel metadata and an action result.

The existing loopback flow remains only as a temporary explicit fallback while
the Web client or Cloudflare service is not configured. It is never selected
silently after a Cloudflare failure.

## Error behaviour

- Google denial: retain no token; show `Доступ Google не предоставлен`.
- Session expiry: retain no token; show `Вход не завершён за 10 минут` and offer
  a fresh attempt.
- Worker/network failure: retain no token; show a retry action and a safe
  diagnostic ID only.
- Consume race or replay: return no token and invalidate the session.

## UX: clear channel connection, not a technical OAuth dialog

### Audience and single job

The operator manages a large set of YouTube channels and needs to know, at a
glance, which exact channel is being connected and what action is required
next. The connection screen has one job: move one selected channel from
`Not connected` to `Connected` without asking the operator to understand
redirects, ports, client secrets, or scopes.

### Visual direction

Keep NewsFlow's dark control-room character, but make the OAuth card feel like
a **channel access pass** rather than a settings form. The one intentional
signature is a horizontal three-stop route line: `This channel` → `Google` →
`YouTube data`. It is semantic progress, not decoration.

- Deep panel: `#0A1F31`; raised card: `#102B3E`; dividers: `#1D3D57`.
- Action blue: `#4BB4FF`; ready green: `#65E1A7`; attention amber: `#F5C76D`;
  blocking red: `#FF8F92`.
- Existing interface type remains the body and utility face. Channel name is
  the single display treatment: 18–20px, semibold, one line with ellipsis and
  its full value exposed by a tooltip.
- Motion is limited to a slow active dot travelling along the route line while
  waiting; it is disabled under `prefers-reduced-motion`.

### Connection card

Selecting `Подключить YouTube` expands a focused card directly beneath that
channel row. It never replaces the entire analytics screen, so large channel
lists remain usable.

```text
┌  Взгляд сверху                                      [Закрыть] ┐
│  ○ Этот канал ───── ● Google ───── ○ Данные YouTube             │
│                                                                  │
│  Откроется отдельное окно Chrome только для этого канала.       │
│  Основной Chrome и другие каналы не будут затронуты.            │
│                                                                  │
│  [Подключить Google]                   Сменить Google-аккаунт  │
└────────────────────────────────────────────────────────────────┘
```

The primary action becomes disabled only after the Worker session is created.
Its label changes consistently to `Ожидаем подтверждение в Google`. The card
then shows a visible ten-minute countdown, `Открыть окно входа снова`, and
`Отменить вход`. It never presents a blank spinner.

### Success and failure states

On success, the route line becomes three green checks and the card shows the
actual channel avatar, real channel name, channel ID on a copyable secondary
line, and subscriber count. The confirmation reads: `Канал подключён`.

Errors name both the outcome and the next action:

| State | Message | Available action |
| --- | --- | --- |
| Google denied access | `Google не предоставил доступ к этому каналу.` | `Начать заново` |
| Timed out | `Вход не завершён за 10 минут.` | `Открыть вход снова` |
| Callback service unavailable | `Не удалось получить ответ от сервиса входа.` | `Повторить` and a safe diagnostic ID |
| Token no longer works | `Доступ канала отозван в Google.` | `Подключить заново` |

`Сменить Google-аккаунт` is visually secondary and opens a confirmation that
names only the selected channel and says that its dedicated Chrome profile and
local token will be cleared. Other channels are explicitly listed as
unaffected.

### Accessibility and resilient lists

- Every state change uses an `aria-live="polite"` status message.
- The primary action, retry, cancel, and account switch have visible keyboard
  focus and can be reached with Tab/Enter.
- Text and icons always duplicate colour meaning; long names wrap or truncate
  safely without moving actions off-screen.
- On narrow screens the route stops stack in order and each action becomes a
  full-width button. On wide screens, only the active row expands; all other
  channel rows keep their compact status badges.

## Required operator configuration

1. Create a Web application OAuth client in the existing Google Cloud project.
2. Register the callback URI above and keep the existing branding, privacy,
   terms, and data-access scopes.
3. Deploy the Worker to `a.tinkbro.online` and configure the client ID, client
   secret, session-encryption secret, and D1 binding as secrets/bindings.
4. Enter only the public client ID and Worker URL in NewsFlow.

Full OAuth scope verification remains required to remove Google's unverified
app warning and to serve more than the unverified-app user cap.

## Verification

- Worker unit tests cover state validation, expiry, one-time consumption,
  Google denial, and removal after consumption.
- Desktop tests cover the pending/poll sequence, safe status messages, local
  token persistence, and the absence of monetary scope by default.
- Integration verification uses a non-public test authorization for `Взгляд
  сверху`, then checks only actual channel name, avatar, ID, and subscriber
  count.
- Package a new executable only after automated checks pass and the user asks
  for it.
