# Cloudflare YouTube OAuth Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace NewsFlow's fragile local-loopback YouTube OAuth completion with a Cloudflare-hosted, one-time OAuth handoff while keeping one protected token and Chrome profile per channel on the local Windows account.

**Architecture:** A Worker mounted at `https://a.tinkbro.online/oauth/youtube/` owns the Google Web OAuth client secret, exchanges the authorization code, encrypts the temporary result in D1, and permits exactly one authenticated desktop consume. Electron starts a background core process for each channel connection so the React UI can show a real waiting state; the Python core receives the result, refreshes the actual channel profile, and persists the token through the existing DPAPI-protected settings mapping.

**Tech Stack:** Cloudflare Workers, D1, Web Crypto, `oauth4webapi`, Vitest with the Cloudflare Workers pool, Python standard-library HTTP client, Electron IPC/child processes, React, TypeScript, existing Windows DPAPI settings protection.

**Spec:** `docs/superpowers/specs/2026-08-31-cloudflare-oauth-handoff-design.md`

## Global Constraints

- The sole Google redirect URI is `https://a.tinkbro.online/oauth/youtube/callback`.
- Use a new Google OAuth client of type **Web application**; do not put its client secret in NewsFlow, `settings.json`, logs, screenshots, or support messages.
- Permanent refresh tokens remain only in `Settings.youtube_oauth_tokens`, which is already persisted as `youtube_oauth_tokens_protected` with Windows DPAPI.
- A session expires after exactly ten minutes; expired, denied, cancelled, and consumed sessions never return token material.
- Keep a separate NewsFlow-owned Chrome `--user-data-dir` per `profile_id`, always start OAuth with `--new-window`, and never reuse the normal Chrome profile.
- Default scopes are upload, read-only channel metadata, and non-monetary YouTube Analytics. Add the monetary Analytics scope only when `includeMonetary` is true.
- `oauth4webapi` is an OAuth **client** protocol dependency. Do not install or use `workers-oauth-provider`, because NewsFlow is not issuing OAuth tokens to third-party MCP clients.
- All Worker secrets are configured by `wrangler secret put`: `GOOGLE_WEB_CLIENT_ID`, `GOOGLE_WEB_CLIENT_SECRET`, and a base64-encoded 32-byte `SESSION_ENCRYPTION_KEY`.
- Keep `oauth-site/index.html`, `oauth-site/privacy/index.html`, and `oauth-site/terms/index.html` publicly available on the same `a.tinkbro.online` domain.
- Do not alter YouTube content or publish a video during development or verification.
- This workspace currently has no `.git` directory. Do not initialize version control merely for this task; execute each listed commit command only if the user later supplies a Git repository, otherwise record the completed file set in the implementation handoff.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `oauth-site/worker/package.json` | Isolated Worker dependencies and scripts; no dependency is added to the Electron bundle. |
| `oauth-site/worker/wrangler.jsonc` | Worker/D1/asset binding and the 5-minute cleanup trigger. |
| `oauth-site/worker/src/contracts.ts` | The narrow, shared runtime types for sessions, scopes, and HTTP results. |
| `oauth-site/worker/src/crypto.ts` | SHA-256 capability hashing and AES-GCM encryption/decryption of the temporary token payload. |
| `oauth-site/worker/src/session-repository.ts` | The only D1 access layer: create, read, transition, consume, cancel, and delete expired sessions. |
| `oauth-site/worker/src/google-oauth.ts` | Google authorization URL construction and authorization-code exchange through `oauth4webapi`. |
| `oauth-site/worker/src/index.ts` | Request routing, CORS-free same-purpose API responses, callback pages, and scheduled cleanup. |
| `oauth-site/worker/migrations/0001_oauth_sessions.sql` | D1 schema and indexes for temporary one-time sessions only. |
| `oauth-site/worker/test/*.test.ts` | Worker unit and endpoint tests using a fake repository or Miniflare D1 binding. |
| `oauth-site/worker/README.md` | Exact deploy/configuration/recovery commands, never containing secret values. |
| `scriptor/youtube_oauth.py` | Desktop HTTP client for create/wait/cancel, safe response validation, and legacy loopback fallback. |
| `scriptor/config.py` | Public Cloudflare handoff URL setting; no Web OAuth secret or token is added. |
| `scriptor/bridge.py` | Channel-specific start/finish/cancel commands, snapshots, profile browser command, and DPAPI persistence. |
| `tests/test_youtube_publisher.py` | Python tests for handoff routing, statuses, scopes, profile isolation, and token persistence. |
| `studio-ui-remotion-verify/electron/main.ts` | Background `NewsFlowCore` OAuth job manager, IPC status/cancel routes, and process cleanup. |
| `studio-ui-remotion-verify/electron/preload.mts` | Safe APIs exposing only OAuth job start/status/cancel to the renderer. |
| `studio-ui-remotion-verify/src/desktop.d.ts` | Typed OAuth handoff snapshot and IPC job interfaces. |
| `studio-ui-remotion-verify/src/ui/App.tsx` | Per-channel access-pass card, timer, retry/cancel/account-switch controls, and live status. |
| `studio-ui-remotion-verify/src/ui/analytics.css` | Accessible visual states, route line, compact rows, responsive layout, and reduced-motion fallback. |

## Session and endpoint contract

The Worker owns the following JSON API. The desktop must not construct Google URLs or call the Google token endpoint itself.

```ts
export type OAuthScopeChoice = { includeMonetary: boolean };

export type CreateSessionResponse = {
  sessionId: string;
  pollCapability: string;
  authorizationUrl: string;
  expiresAt: string;
};

export type SessionResult =
  | { status: 'pending'; expiresAt: string }
  | { status: 'denied' | 'expired' | 'cancelled' | 'consumed'; diagnosticId: string }
  | { status: 'ready'; credentials: Record<string, unknown> };

// POST /oauth/youtube/sessions
// body: { channelProfileId: string, includeMonetary: boolean }
// response: CreateSessionResponse
// POST /oauth/youtube/sessions/:sessionId/consume
// header: Authorization: Bearer <pollCapability>
// response: SessionResult
// POST /oauth/youtube/sessions/:sessionId/cancel
// header: Authorization: Bearer <pollCapability>
// response: { status: 'cancelled' | 'consumed' | 'expired' }
```

No endpoint accepts a return URL, a supplied scope string, a Google password, a browser cookie, or an OAuth client secret. `channelProfileId` is a local correlation identifier only and is never rendered to the user or sent to Google.

### Task 1: Scaffold the isolated Worker and D1 schema

**Files:**
- Create: `oauth-site/worker/package.json`
- Create: `oauth-site/worker/tsconfig.json`
- Create: `oauth-site/worker/vitest.config.ts`
- Create: `oauth-site/worker/wrangler.jsonc`
- Create: `oauth-site/worker/migrations/0001_oauth_sessions.sql`
- Create: `oauth-site/worker/src/contracts.ts`
- Create: `oauth-site/worker/test/contracts.test.ts`

**Interfaces:**
- Consumes: the callback URL and ten-minute lifetime from the spec.
- Produces: `Env`, `OAuthSessionRecord`, `CreateSessionResponse`, and `SessionResult` used by all Worker modules.

- [ ] **Step 1: Write the failing contract and schema test.**

```ts
import { describe, expect, it } from 'vitest';
import { SESSION_TTL_MS, allowedScopes } from '../src/contracts';

describe('OAuth handoff contract', () => {
  it('keeps a session alive for exactly ten minutes and omits money by default', () => {
    expect(SESSION_TTL_MS).toBe(10 * 60 * 1000);
    expect(allowedScopes(false)).toEqual([
      'https://www.googleapis.com/auth/youtube.upload',
      'https://www.googleapis.com/auth/youtube.readonly',
      'https://www.googleapis.com/auth/yt-analytics.readonly',
    ]);
  });
});
```

- [ ] **Step 2: Run the new test and verify it fails because the Worker source does not exist.**

Run: `cd oauth-site/worker; pnpm test --run test/contracts.test.ts`

Expected: FAIL with a module-not-found error for `../src/contracts`.

- [ ] **Step 3: Add Worker package configuration and the source contract.**

Create a `package.json` with scripts `test`, `test:watch`, `typecheck`, `dev`, and `deploy`; add `oauth4webapi`, `vitest`, `@cloudflare/vitest-pool-workers`, `typescript`, and `wrangler`. Configure the Workers pool in `vitest.config.ts` and use `compatibility_date` equal to the deployment date.

Implement these exact exports in `src/contracts.ts`:

```ts
export const SESSION_TTL_MS = 10 * 60 * 1000;
export const CALLBACK_PATH = '/oauth/youtube/callback';
export const API_PREFIX = '/oauth/youtube';
export const allowedScopes = (includeMonetary: boolean): string[] => [
  'https://www.googleapis.com/auth/youtube.upload',
  'https://www.googleapis.com/auth/youtube.readonly',
  'https://www.googleapis.com/auth/yt-analytics.readonly',
  ...(includeMonetary ? ['https://www.googleapis.com/auth/yt-analytics-monetary.readonly'] : []),
];

export interface Env {
  OAUTH_SESSIONS: D1Database;
  ASSETS: Fetcher;
  GOOGLE_WEB_CLIENT_ID: string;
  GOOGLE_WEB_CLIENT_SECRET: string;
  SESSION_ENCRYPTION_KEY: string;
}
```

The SQL migration must create `oauth_sessions` with: `id`, `state_hash`, `poll_capability_hash`, `profile_id`, `include_monetary`, `code_verifier_encrypted`, `credentials_encrypted`, `status`, `diagnostic_id`, `expires_at`, and `created_at`. Add indexes for `state_hash` and `expires_at`. Do not include a plaintext access token, refresh token, poll capability, or code verifier column.

- [ ] **Step 4: Run contract, type, and migration checks.**

Run: `cd oauth-site/worker; pnpm test --run test/contracts.test.ts; pnpm typecheck; pnpm wrangler d1 migrations apply OAUTH_SESSIONS --local`

Expected: PASS; the local D1 migration creates one `oauth_sessions` table.

- [ ] **Step 5: Commit the isolated Worker scaffold.**

```bash
git add oauth-site/worker
git commit -m "feat: scaffold Cloudflare OAuth handoff worker"
```

### Task 2: Implement crypto and one-time D1 session repository

**Files:**
- Create: `oauth-site/worker/src/crypto.ts`
- Create: `oauth-site/worker/src/session-repository.ts`
- Create: `oauth-site/worker/test/crypto.test.ts`
- Create: `oauth-site/worker/test/session-repository.test.ts`

**Interfaces:**
- Consumes: `Env`, `SESSION_TTL_MS`, and Worker Web Crypto.
- Produces: `sha256Base64Url(value: string): Promise<string>`, `encryptJson(value, key): Promise<string>`, `decryptJson<T>(ciphertext, key): Promise<T>`, and `SessionRepository` methods below.

```ts
export interface SessionRepository {
  create(input: PendingSession): Promise<void>;
  findByState(state: string, now: number): Promise<OAuthSessionRecord | null>;
  markReady(id: string, credentialsEncrypted: string): Promise<boolean>;
  markDenied(id: string, diagnosticId: string): Promise<void>;
  consume(id: string, pollCapability: string, now: number): Promise<SessionResult>;
  cancel(id: string, pollCapability: string, now: number): Promise<'cancelled' | 'expired' | 'consumed'>;
  deleteExpired(now: number): Promise<number>;
}
```

- [ ] **Step 1: Write failing tests for confidentiality and replay resistance.**

```ts
it('round-trips encrypted JSON without putting its plaintext in the ciphertext', async () => {
  const encrypted = await encryptJson({ refresh_token: 'refresh-secret' }, key);
  expect(encrypted).not.toContain('refresh-secret');
  await expect(decryptJson<{ refresh_token: string }>(encrypted, key))
    .resolves.toEqual({ refresh_token: 'refresh-secret' });
});

it('returns credentials once and reports consumed on the replay', async () => {
  await repository.create(pendingSession);
  await repository.markReady(pendingSession.id, encryptedCredentials);
  expect((await repository.consume(pendingSession.id, capability, now)).status).toBe('ready');
  expect((await repository.consume(pendingSession.id, capability, now)).status).toBe('consumed');
});
```

- [ ] **Step 2: Run these tests to confirm the missing module failures.**

Run: `cd oauth-site/worker; pnpm test --run test/crypto.test.ts test/session-repository.test.ts`

Expected: FAIL because crypto and repository implementations are absent.

- [ ] **Step 3: Implement authenticated encryption and transactional transitions.**

Use `crypto.subtle.importKey('raw', base64UrlDecode(env.SESSION_ENCRYPTION_KEY), { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])`. Generate a fresh 12-byte IV for every encryption and serialize `{v:1,iv,ciphertext}` as base64url JSON. Hash opaque values with SHA-256 before writing D1.

`consume` must use a D1 batch/conditional update sequence that verifies `status='ready'`, the hash of the presented capability, and `expires_at > now`. It must delete the row only after obtaining its encrypted credential field, then decrypt only for the successful response. A wrong capability returns `consumed`, never `ready`; the status response must not reveal whether an ID exists. `cancel` must delete only a pending/denied record with the matching capability and return `consumed` for a ready or previously consumed record.

- [ ] **Step 4: Run unit tests, including expiry and cancellation.**

Run: `cd oauth-site/worker; pnpm test --run test/crypto.test.ts test/session-repository.test.ts; pnpm typecheck`

Expected: PASS, including tests for wrong capability, expired session, cancellation, and a second consume.

- [ ] **Step 5: Commit the one-time storage layer.**

```bash
git add oauth-site/worker/src oauth-site/worker/test
git commit -m "feat: add encrypted one-time OAuth sessions"
```

### Task 3: Implement Google client flow and Worker HTTP endpoints

**Files:**
- Create: `oauth-site/worker/src/google-oauth.ts`
- Create: `oauth-site/worker/src/index.ts`
- Create: `oauth-site/worker/test/google-oauth.test.ts`
- Create: `oauth-site/worker/test/worker-routes.test.ts`

**Interfaces:**
- Consumes: `SessionRepository`, `allowedScopes`, `Env`, `https://accounts.google.com/o/oauth2/v2/auth`, and `https://oauth2.googleapis.com/token`.
- Produces: `createAuthorizationRequest(env, session): Promise<string>` and a Worker `fetch(request, env, ctx)` handler.

- [ ] **Step 1: Write failing route tests for start, callback, and denial.**

```ts
it('creates a fixed-callback authorization URL with PKCE and no money scope by default', async () => {
  const response = await worker.fetch(new Request('https://a.tinkbro.online/oauth/youtube/sessions', {
    method: 'POST', body: JSON.stringify({ channelProfileId: 'profile-a', includeMonetary: false }),
  }), env, ctx);
  const body = await response.json() as CreateSessionResponse;
  expect(new URL(body.authorizationUrl).searchParams.get('redirect_uri'))
    .toBe('https://a.tinkbro.online/oauth/youtube/callback');
  expect(new URL(body.authorizationUrl).searchParams.get('scope'))
    .not.toContain('yt-analytics-monetary');
});

it('renders a completion page and makes the credentials consumable once', async () => {
  mockGoogleTokenExchange({ access_token: 'access', refresh_token: 'refresh', expires_in: 3600, token_type: 'Bearer' });
  const callback = await worker.fetch(new Request(`https://a.tinkbro.online/oauth/youtube/callback?state=${state}&code=code-a`), env, ctx);
  expect(await callback.text()).toContain('Вернитесь в NewsFlow');
  expect((await consume(sessionId, capability)).status).toBe('ready');
});
```

- [ ] **Step 2: Run the endpoint tests and verify they fail.**

Run: `cd oauth-site/worker; pnpm test --run test/google-oauth.test.ts test/worker-routes.test.ts`

Expected: FAIL because the authorization client and fetch handler do not exist.

- [ ] **Step 3: Implement the Worker flow using `oauth4webapi`.**

Create a random state, random poll capability, and PKCE verifier per session. Store only hashes/encrypted values. Build Google authorization requests with these exact parameters: `response_type=code`, `access_type=offline`, `prompt=consent`, `code_challenge_method=S256`, and the fixed callback URL. Use `authorizationCodeGrantRequest` with the Worker-held client secret and stored verifier to exchange a successful callback code.

Route only these methods and paths:

```ts
POST /oauth/youtube/sessions
GET  /oauth/youtube/callback
POST /oauth/youtube/sessions/:id/consume
POST /oauth/youtube/sessions/:id/cancel
```

Return JSON with `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, and `X-Content-Type-Options: nosniff`. The callback page must set the same no-store policy and render only safe fixed Russian messages. It must not echo `code`, `state`, email, channel name, token data, or raw Google error descriptions. Unmatched paths must be delegated to `env.ASSETS.fetch(request)` so the existing home, privacy, and terms pages continue to work.

For a Google `error`, mark the session denied and render `Доступ Google не предоставлен. Вернитесь в NewsFlow.` For an invalid/expired state, render HTTP 400 without exposing session identity. Implement `scheduled()` to call `deleteExpired(Date.now())`.

- [ ] **Step 4: Run all Worker checks.**

Run: `cd oauth-site/worker; pnpm test --run; pnpm typecheck; pnpm wrangler dev --local --test-scheduled`

Expected: all tests pass; a local request to `/privacy/` serves the existing static privacy page while Worker API endpoints remain dynamic.

- [ ] **Step 5: Commit the complete Worker behavior.**

```bash
git add oauth-site/worker
git commit -m "feat: implement Google OAuth callback handoff"
```

### Task 4: Document and configure a safe Cloudflare deployment

**Files:**
- Modify: `oauth-site/README.md`
- Create: `oauth-site/worker/README.md`
- Modify: `oauth-site/worker/wrangler.jsonc`
- Modify: `tests/test_oauth_site.py`

**Interfaces:**
- Consumes: deployed D1 binding `OAUTH_SESSIONS` and the verified domain `a.tinkbro.online`.
- Produces: reproducible operator steps that leave no credentials in version control or NewsFlow.

- [ ] **Step 1: Write the failing documentation assertions.**

Add `tests/test_oauth_site.py` assertions that the Worker README contains `wrangler secret put GOOGLE_WEB_CLIENT_SECRET`, `wrangler d1 migrations apply`, and the exact callback URL, and does not contain a string matching a Google client secret JSON value.

- [ ] **Step 2: Run the documentation test and verify it fails before the Worker README exists.**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_worker_readme_uses_secrets_not_client_json`

Expected: FAIL with a missing-file assertion.

- [ ] **Step 3: Write the deploy guide with exact commands and rollback.**

Document these operations in order:

```powershell
cd oauth-site/worker
pnpm install --frozen-lockfile
pnpm wrangler d1 create newsflow-oauth-sessions
# copy the returned database_id into wrangler.jsonc; do not add a credential
pnpm wrangler d1 migrations apply OAUTH_SESSIONS --remote
pnpm wrangler secret put GOOGLE_WEB_CLIENT_ID
pnpm wrangler secret put GOOGLE_WEB_CLIENT_SECRET
pnpm wrangler secret put SESSION_ENCRYPTION_KEY
pnpm wrangler deploy
```

Then document the Google Cloud action: create a **Web application** OAuth client in the existing project and register only `https://a.tinkbro.online/oauth/youtube/callback`. Point the existing `a.tinkbro.online` custom domain Worker at this deployment, which serves the files already in `oauth-site`; verify `/`, `/privacy/`, `/terms/`, and `/oauth/youtube/callback` after deployment. State that the current Desktop client remains only for explicit legacy fallback and the Web client secret must never be downloaded into NewsFlow.

Include rollback: reattach the previous static Worker to `a.tinkbro.online`, then revoke/delete the new Web client if the deployment is abandoned; do not revoke channel refresh tokens during a website rollback.

- [ ] **Step 4: Run the documentation test and static config checks.**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_worker_readme_uses_secrets_not_client_json; cd oauth-site/worker; pnpm wrangler deploy --dry-run`

Expected: PASS; dry run has no secret value in output.

- [ ] **Step 5: Commit deployment documentation.**

```bash
git add oauth-site tests/test_oauth_site.py
git commit -m "docs: add Cloudflare OAuth handoff deployment guide"
```

### Task 5: Add the Python Cloudflare handoff client with explicit fallback

**Files:**
- Modify: `scriptor/youtube_oauth.py`
- Modify: `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes: a configured HTTPS base URL, selected profile browser command, `include_monetary`, and `youtube_oauth_scopes`.
- Produces:

```python
@dataclass(frozen=True)
class CloudflareOAuthSession:
    session_id: str
    poll_capability: str
    authorization_url: str
    expires_at: datetime

def start_cloudflare_channel_authorization(service_url: str, profile_id: str, *, include_monetary: bool) -> CloudflareOAuthSession: ...
def open_channel_authorization(browser_command: str, authorization_url: str) -> None: ...
def wait_for_cloudflare_credentials(service_url: str, session: CloudflareOAuthSession, *, timeout_seconds: float = 600.0, poll_seconds: float = 1.5) -> dict[str, Any]: ...
def cancel_cloudflare_authorization(service_url: str, session: CloudflareOAuthSession) -> None: ...
```

- [ ] **Step 1: Write failing Python tests for the handoff request and safe error mapping.**

```python
def test_cloudflare_start_uses_only_profile_id_and_boolean_scope_choice(self):
    with patch('scriptor.youtube_oauth.urlopen') as open_url:
        start_cloudflare_channel_authorization('https://a.tinkbro.online', 'profile-a', include_monetary=False)
    request = open_url.call_args.args[0]
    self.assertEqual(request.full_url, 'https://a.tinkbro.online/oauth/youtube/sessions')
    self.assertNotIn('refresh_token', request.data.decode())
    self.assertIn(b'"includeMonetary": false', request.data)

def test_cloudflare_wait_turns_denial_into_a_safe_russian_error(self):
    with self.assertRaisesRegex(RuntimeError, 'Доступ Google не предоставлен'):
        wait_for_cloudflare_credentials('https://a.tinkbro.online', denied_session, timeout_seconds=0)
```

- [ ] **Step 2: Run the focused tests to verify failure.**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests.test_cloudflare_start_uses_only_profile_id_and_boolean_scope_choice tests.test_youtube_publisher.PublicationJobTests.test_cloudflare_wait_turns_denial_into_a_safe_russian_error`

Expected: FAIL with missing `start_cloudflare_channel_authorization` and `wait_for_cloudflare_credentials` imports.

- [ ] **Step 3: Implement bounded HTTP and browser helpers.**

Use `urllib.request.Request` with JSON `Content-Type`, 15-second network timeouts, an HTTPS-only normalized base URL, and a fixed API prefix. Validate all response fields before use: session ID/capability must be opaque URL-safe strings, `authorizationUrl` must be HTTPS and hosted by `accounts.google.com`, and credentials must contain a non-empty `refresh_token` or a valid usable token response.

Poll `consume` with the bearer capability until ready, denial, expiry, cancellation, or the supplied deadline. Never log or include raw HTTP bodies in errors. Map states exactly to:

```python
{
    'denied': 'Доступ Google не предоставлен',
    'expired': 'Вход не завершён за 10 минут',
    'cancelled': 'Вход в Google отменён',
    'consumed': 'Сессия входа уже использована. Начните заново.',
}
```

Keep `authorize_desktop_channel` unchanged as `authorize_loopback_channel`; call it only when no valid Cloudflare service URL exists. Do not fall back after a Cloudflare response or timeout.

- [ ] **Step 4: Run all OAuth helper tests.**

Run: `python -m unittest tests.test_youtube_publisher -v`

Expected: PASS, including existing default-scope, `--new-window`, and token serialization tests.

- [ ] **Step 5: Commit the Python handoff client.**

```bash
git add scriptor/youtube_oauth.py tests/test_youtube_publisher.py
git commit -m "feat: add Cloudflare OAuth handoff client"
```

### Task 6: Add persisted public configuration and channel-safe core commands

**Files:**
- Modify: `scriptor/config.py`
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes: `CloudflareOAuthSession`, the existing `fetch_current_channel`, and `Settings.youtube_oauth_tokens`.
- Produces the bridge commands below:

```text
save-youtube-oauth-service { serviceUrl: string }
start-youtube-channel-handoff { index: number, includeMonetary: boolean }
finish-youtube-channel-handoff { index: number, session: CloudflareOAuthSession JSON }
cancel-youtube-channel-handoff { session: CloudflareOAuthSession JSON }
```

- [ ] **Step 1: Write failing tests for configuration persistence and per-channel completion.**

```python
def test_cloudflare_service_url_is_saved_publicly_but_tokens_remain_dpapi_protected(self):
    settings = Settings()
    bridge.save_youtube_oauth_service({'serviceUrl': 'https://a.tinkbro.online'})
    self.assertEqual(settings.youtube_oauth_service_url, 'https://a.tinkbro.online')
    payload = config.settings_payload(settings)
    self.assertNotIn('youtube_oauth_tokens', payload)
    self.assertIn('youtube_oauth_tokens_protected', payload)

def test_handoff_completion_saves_only_the_selected_profile_token(self):
    settings = Settings(analytics_channels=[{'profile_id': 'a'}, {'profile_id': 'b'}])
    # Patch wait_for_cloudflare_credentials and fetch_current_channel.
    bridge.finish_youtube_channel_handoff({'index': 0, 'session': session_json})
    self.assertIn('a', settings.youtube_oauth_tokens)
    self.assertNotIn('b', settings.youtube_oauth_tokens)
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests.test_cloudflare_service_url_is_saved_publicly_but_tokens_remain_dpapi_protected tests.test_youtube_publisher.PublicationJobTests.test_handoff_completion_saves_only_the_selected_profile_token`

Expected: FAIL because the setting and commands do not exist.

- [ ] **Step 3: Implement settings and command boundaries.**

Add `youtube_oauth_service_url: str = ''` to `Settings`, load/save it as ordinary non-secret configuration, and expose snapshot data as:

```python
"analyticsOAuth": {
    "configured": bool(valid_service_url),
    "mode": "cloudflare" if valid_service_url else "loopback",
    "serviceUrl": valid_service_url,
    "fileName": Path(settings.google_oauth_client_file).name if settings.google_oauth_client_file else "",
}
```

`start-youtube-channel-handoff` validates the selected row, ensures a persistent `profile_id`, creates its profile directory, creates the Worker session, opens its `authorization_url` with `_youtube_oauth_browser_command(profile_dir)`, and returns only the serialized session metadata plus a safe status. It never returns a poll capability to the React snapshot.

`finish-youtube-channel-handoff` waits/consumes, runs `fetch_current_channel(credentials)`, writes only that profile's serialized refreshed token to `youtube_oauth_tokens`, updates name/avatar/channel ID/subscribers/views, records the existing activity entry, and calls `save_settings`. `cancel-youtube-channel-handoff` calls the Worker cancel endpoint and persists no token. Preserve `connect-youtube-channel` as an explicitly named loopback compatibility command rather than silently selecting it.

- [ ] **Step 4: Run core test suite and inspect serialized settings.**

Run: `python -m unittest tests.test_youtube_publisher; python -m unittest tests.test_security tests.test_core`

Expected: PASS; a saved settings fixture includes `youtube_oauth_service_url` and still contains no plaintext refresh token.

- [ ] **Step 5: Commit core orchestration.**

```bash
git add scriptor/config.py scriptor/bridge.py tests/test_youtube_publisher.py
git commit -m "feat: connect channels through Cloudflare OAuth handoff"
```

### Task 7: Manage non-blocking OAuth jobs in Electron

**Files:**
- Modify: `studio-ui-remotion-verify/electron/main.ts`
- Modify: `studio-ui-remotion-verify/electron/preload.mts`
- Modify: `studio-ui-remotion-verify/electron/tsconfig.json`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Create: `studio-ui-remotion-verify/electron/main.oauth-jobs.test.mts`

**Interfaces:**
- Consumes: the core commands from Task 6 and `spawn`/`execFile`.
- Produces a preload API:

```ts
type OAuthJobState = 'waiting' | 'succeeded' | 'failed' | 'cancelled';
type OAuthJob = { id: string; channelIndex: number; state: OAuthJobState; expiresAt: string; message?: string };

startYoutubeOAuthHandoff(input: { index: number; includeMonetary: boolean }): Promise<OAuthJob>;
getYoutubeOAuthHandoff(id: string): Promise<OAuthJob | null>;
cancelYoutubeOAuthHandoff(id: string): Promise<OAuthJob>;
```

- [ ] **Step 1: Write failing tests for job isolation and cancellation.**

```ts
it('keeps one waiting child process per selected channel and reports completion without blocking IPC', async () => {
  const job = await jobs.start({ index: 2, includeMonetary: false });
  expect(job.state).toBe('waiting');
  expect(spawn).toHaveBeenCalledTimes(1);
});

it('kills only the cancelled job and calls the core cancellation command with its private session metadata', async () => {
  await jobs.cancel('job-a');
  expect(children.get('job-a')?.killed).toBe(true);
  expect(callCore).toHaveBeenCalledWith('cancel-youtube-channel-handoff', expect.any(Object));
});
```

- [ ] **Step 2: Run the Electron test and verify it fails.**

Run: `cd studio-ui-remotion-verify; pnpm exec vitest run electron/main.oauth-jobs.test.mts`

Expected: FAIL because `YoutubeOAuthJobManager` is not exported.

- [ ] **Step 3: Implement a private main-process job manager.**

Create `YoutubeOAuthJobManager` in `electron/main.ts`. It must first call `start-youtube-channel-handoff`, keep the returned session metadata in a `Map<string, PrivateJob>`, then spawn `finish-youtube-channel-handoff` as a background core process. Capture its final JSON response; convert it to `succeeded` or `failed` without putting the session capability or credentials in IPC. Reject a second start for the same channel index while its job is waiting.

On cancellation, call `cancel-youtube-channel-handoff` through `callCore`, terminate only that job's child process, and retain an in-memory `cancelled` status long enough for the renderer to display it. On app quit, cancel every waiting job before exiting. Register IPC handlers named `newsflow:youtube-oauth-start`, `newsflow:youtube-oauth-status`, and `newsflow:youtube-oauth-cancel`; expose only the typed methods from `preload.mts`.

- [ ] **Step 4: Run Electron type and job tests.**

Run: `cd studio-ui-remotion-verify; pnpm exec vitest run electron/main.oauth-jobs.test.mts; pnpm typecheck; pnpm build:desktop`

Expected: PASS; no IPC result contains `pollCapability`, `refresh_token`, or `access_token`.

- [ ] **Step 5: Commit background OAuth job support.**

```bash
git add studio-ui-remotion-verify/electron studio-ui-remotion-verify/src/desktop.d.ts
git commit -m "feat: run YouTube OAuth handoffs in background"
```

### Task 8: Build the channel access-pass UX

**Files:**
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/analytics.css`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Create: `studio-ui-remotion-verify/src/ui/AnalyticsOAuthCard.test.tsx`

**Interfaces:**
- Consumes: `analyticsOAuth.mode`, `OAuthJob`, channel metadata, and the preload job API.
- Produces: a compact channel-row expansion whose only side effect is starting/cancelling the selected channel OAuth handoff.

- [ ] **Step 1: Write failing renderer tests for visible states and keyboard behavior.**

```tsx
it('shows the selected channel route and a ten-minute countdown after a handoff starts', async () => {
  render(<AnalyticsOAuthCard channel={channel} job={{ ...job, state: 'waiting' }} />);
  expect(screen.getByText('Этот канал')).toBeVisible();
  expect(screen.getByText(/Ожидаем подтверждение в Google/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Отменить вход' })).toBeEnabled();
});

it('uses a live region and does not show token or diagnostic internals', () => {
  render(<AnalyticsOAuthCard channel={channel} job={{ ...job, state: 'failed', message: 'Не удалось получить ответ от сервиса входа.' }} />);
  expect(screen.getByRole('status')).toHaveTextContent('Не удалось получить ответ от сервиса входа.');
  expect(screen.queryByText(/refresh_token|pollCapability/i)).toBeNull();
});
```

- [ ] **Step 2: Run the renderer test and verify it fails.**

Run: `cd studio-ui-remotion-verify; pnpm exec vitest run src/ui/AnalyticsOAuthCard.test.tsx`

Expected: FAIL because the component is absent.

- [ ] **Step 3: Implement the focused, accessible card and configuration copy.**

Replace the current file-picker-first controls with Cloudflare status: `Сервис входа готов` for the valid service URL and `Нужна настройка сервиса входа` otherwise. Retain the Desktop JSON picker only in an explicitly labelled `Резервный локальный вход` disclosure.

For each selected channel, render the access pass beneath its existing row:

```text
Этот канал  →  Google  →  Данные YouTube
```

Before start, primary text is `Подключить Google`. While waiting it reads `Ожидаем подтверждение в Google`, shows a `10:00` countdown decreasing from the job expiry, a secondary `Открыть окно входа снова`, and `Отменить вход`. The account switch button asks confirmation naming the selected channel, then invokes only `reset-youtube-channel-account` for that index.

Success uses three green checks and displays returned/public channel avatar, actual name, copyable ID, and subscriber count. Error messages must be the four safe strings in the spec, paired with `Начать заново` or `Повторить`. Put each change into `<div role="status" aria-live="polite">`; retain focus on the action that follows a terminal state.

Add CSS using the approved palette: `#0A1F31`, `#102B3E`, `#1D3D57`, `#4BB4FF`, `#65E1A7`, `#F5C76D`, and `#FF8F92`. Make focus outlines visible; stack route nodes/actions under 720px; disable the travelling active-dot animation with `@media (prefers-reduced-motion: reduce)`.

- [ ] **Step 4: Run renderer and build validation.**

Run: `cd studio-ui-remotion-verify; pnpm exec vitest run src/ui/AnalyticsOAuthCard.test.tsx; pnpm typecheck; pnpm build:web`

Expected: PASS; no snapshot or rendered DOM contains token/capability names.

- [ ] **Step 5: Commit the OAuth access-pass UI.**

```bash
git add studio-ui-remotion-verify/src/ui/App.tsx studio-ui-remotion-verify/src/ui/analytics.css studio-ui-remotion-verify/src/desktop.d.ts studio-ui-remotion-verify/src/ui/AnalyticsOAuthCard.test.tsx
git commit -m "feat: add channel OAuth access pass"
```

### Task 9: Verify the complete handoff, preserve fallback, and package deliberately

**Files:**
- Modify: `README.md`
- Modify: `studio-ui-remotion-verify/package.json`
- Modify: `studio-ui-remotion-verify/scripts/verify-core-runtime.mjs`
- Modify: `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes: deployed Worker URL, a non-public Google test authorization, and the new packaged core.
- Produces: a verified portable NewsFlow build only after worker, Python, Electron, and UI tests succeed.

- [ ] **Step 1: Write failing release-guard tests.**

```python
def test_cloudflare_mode_never_invokes_loopback_after_a_remote_failure(self):
    with patch.object(bridge, 'wait_for_cloudflare_credentials', side_effect=RuntimeError('Вход не завершён за 10 минут')), \
         patch.object(bridge, 'authorize_desktop_channel') as loopback:
        with self.assertRaisesRegex(RuntimeError, '10 минут'):
            bridge.finish_youtube_channel_handoff({'index': 0, 'session': session_json})
    loopback.assert_not_called()
```

- [ ] **Step 2: Run the regression test and verify the current implementation fails before its guard is added.**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests.test_cloudflare_mode_never_invokes_loopback_after_a_remote_failure`

Expected: FAIL until the no-silent-fallback implementation from Task 6 is complete.

- [ ] **Step 3: Add concise operator documentation and runtime packaging checks.**

In `README.md`, add the exact user sequence: configure Worker URL, add a channel, click `Подключить Google`, complete Google in the separate Chrome window, return to NewsFlow, and verify the actual channel identity. Explain that each channel is a separate Google login/token and that Cloudflare retains temporary encrypted data only until consumption or the ten-minute expiry.

Update the package version/output directory and `.core-bin-*` input only after the source and tests pass. Extend `verify-core-runtime.mjs` to assert that the packaged core includes the new `scriptor/youtube_oauth.py` cloud functions and the Electron bundle exposes the three OAuth handoff IPC methods.

- [ ] **Step 4: Run the entire verification matrix.**

Run:

```powershell
python -m unittest tests.test_youtube_publisher tests.test_oauth_site tests.test_security tests.test_core
cd oauth-site/worker; pnpm test --run; pnpm typecheck
cd ..\..\studio-ui-remotion-verify; pnpm typecheck; pnpm build; pnpm verify:core-runtime
```

Expected: every command exits 0; no test mocks or logs expose Google credentials.

- [ ] **Step 5: Perform one manual non-publishing acceptance check after deployment.**

Use a dedicated test channel only. Start a channel handoff, consent in the dedicated Chrome profile, wait for the green success card, and check only channel name, avatar, ID, and subscriber count. Then use `Сменить Google-аккаунт` and verify that only the selected channel loses its local token/profile; do not upload or modify a video.

- [ ] **Step 6: Build and verify the portable executable after the user requests the build.**

Run:

```powershell
cd studio-ui-remotion-verify
pnpm package:preview
pnpm verify:portable
```

Expected: a new portable executable references the new core build and passes the portable runtime check. Report its exact local path and the Worker deployment version, but never include secrets or tokens.

- [ ] **Step 7: Commit final integration work.**

```bash
git add README.md studio-ui-remotion-verify/package.json studio-ui-remotion-verify/scripts/verify-core-runtime.mjs tests/test_youtube_publisher.py
git commit -m "feat: ship Cloudflare YouTube OAuth handoff"
```

## Self-review

- Spec coverage: Tasks 1–3 implement the required Worker session lifecycle, fixed callback, encryption, expiry, denial and single use. Task 4 handles deployment and retains the public static pages. Tasks 5–6 implement the desktop callback client, explicit fallback, profile isolation, DPAPI token persistence, and safe errors. Tasks 7–8 implement the non-blocking and accessible channel UX. Task 9 verifies the no-fallback guarantee, packaging, and non-publishing end-to-end check.
- Placeholder scan: no deferred implementation markers, unspecified error handling, or unspecified tests remain; each code task has an exact test command and expected outcome.
- Type consistency: Worker `CreateSessionResponse` and `SessionResult` drive Python session methods; Python bridge commands drive Electron job methods; Electron job types drive the React card. The Worker never exposes permanent credentials outside one successful consume and Electron never exposes the poll capability to the renderer.
