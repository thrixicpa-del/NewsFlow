import { API_PREFIX, CALLBACK_PATH, SESSION_TTL_MS, type CreateSessionResponse, type Env } from './contracts';
import { decryptJson, encryptJson } from './crypto';
import { createGoogleAuthorizationUrl, exchangeGoogleAuthorizationCode } from './google-oauth';
import { D1SessionRepository } from './session-repository';

const opaque = (): string => {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let value = '';
  bytes.forEach((byte) => { value += String.fromCharCode(byte); });
  return btoa(value).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
};

const diagnosticId = (): string => crypto.randomUUID().replaceAll('-', '').slice(0, 12);

const securityHeaders = {
  'cache-control': 'no-store',
  'referrer-policy': 'no-referrer',
  'x-content-type-options': 'nosniff',
};

const json = (value: unknown, status = 200): Response => new Response(JSON.stringify(value), {
  status,
  headers: { ...securityHeaders, 'content-type': 'application/json; charset=utf-8' },
});

const page = (text: string, status = 200): Response => new Response(`<!doctype html><html lang="ru"><meta charset="utf-8"><title>NewsFlow</title><body><main><h1>${text}</h1></main></body></html>`, {
  status,
  headers: { ...securityHeaders, 'content-type': 'text/html; charset=utf-8' },
});

const bearer = (request: Request): string => {
  const match = /^Bearer ([A-Za-z0-9_-]{32,128})$/u.exec(request.headers.get('authorization') || '');
  return match?.[1] || '';
};

const sessionPath = new RegExp(`^${API_PREFIX}/sessions/([A-Za-z0-9_-]{16,128})/(consume|cancel)$`);

const requestBody = async (request: Request): Promise<{ channelProfileId: string; includeMonetary: boolean } | null> => {
  const value: unknown = await request.json().catch(() => null);
  if (!value || typeof value !== 'object') return null;
  const body = value as Record<string, unknown>;
  const profileId = typeof body.channelProfileId === 'string' ? body.channelProfileId.trim() : '';
  if (!/^[A-Za-z0-9_-]{1,128}$/u.test(profileId) || typeof body.includeMonetary !== 'boolean') return null;
  return { channelProfileId: profileId, includeMonetary: body.includeMonetary };
};

export const handleRequest = async (request: Request, env: Env): Promise<Response> => {
  const url = new URL(request.url);
  const repository = new D1SessionRepository(env.OAUTH_SESSIONS, env.SESSION_ENCRYPTION_KEY);
  if (request.method === 'POST' && url.pathname === `${API_PREFIX}/sessions`) {
    const body = await requestBody(request);
    if (!body) return json({ error: 'invalid_request' }, 400);
    const now = Date.now();
    const sessionId = opaque();
    const state = opaque();
    const pollCapability = opaque();
    const codeVerifier = opaque() + opaque();
    const expiresAt = now + SESSION_TTL_MS;
    await repository.create({
      id: sessionId, state, pollCapability, profileId: body.channelProfileId, includeMonetary: body.includeMonetary,
      codeVerifierEncrypted: await encryptJson(codeVerifier, env.SESSION_ENCRYPTION_KEY), diagnosticId: diagnosticId(), createdAt: now, expiresAt,
    });
    const result: CreateSessionResponse = {
      sessionId,
      pollCapability,
      authorizationUrl: await createGoogleAuthorizationUrl({
        clientId: env.GOOGLE_WEB_CLIENT_ID, serviceOrigin: url.origin, state, codeVerifier, includeMonetary: body.includeMonetary,
      }),
      expiresAt: new Date(expiresAt).toISOString(),
    };
    return json(result, 201);
  }

  if (request.method === 'GET' && url.pathname === CALLBACK_PATH) {
    const state = url.searchParams.get('state') || '';
    const session = state ? await repository.findByState(state, Date.now()) : null;
    if (!session) return page('Ссылка входа недействительна или устарела.', 400);
    if (url.searchParams.has('error')) {
      await repository.markDenied(session.id, session.diagnosticId);
      return page('Доступ Google не предоставлен. Вернитесь в NewsFlow.');
    }
    const code = url.searchParams.get('code') || '';
    if (!code) {
      await repository.markDenied(session.id, session.diagnosticId);
      return page('Вход Google не завершён. Вернитесь в NewsFlow.', 400);
    }
    try {
      const codeVerifier = await decryptJson<string>(session.codeVerifierEncrypted, env.SESSION_ENCRYPTION_KEY);
      const credentials = await exchangeGoogleAuthorizationCode({
        clientId: env.GOOGLE_WEB_CLIENT_ID, clientSecret: env.GOOGLE_WEB_CLIENT_SECRET,
        serviceOrigin: url.origin, code, codeVerifier,
      });
      await repository.markReady(session.id, await encryptJson(credentials, env.SESSION_ENCRYPTION_KEY));
      return page('Канал подключён. Вернитесь в NewsFlow.');
    } catch {
      await repository.markDenied(session.id, session.diagnosticId);
      return page('Не удалось завершить вход. Вернитесь в NewsFlow и начните заново.', 400);
    }
  }

  const match = sessionPath.exec(url.pathname);
  if (request.method === 'POST' && match) {
    const [, sessionId, action] = match;
    const capability = bearer(request);
    if (!capability) return json({ error: 'not_found' }, 404);
    if (action === 'consume') return json(await repository.consume(sessionId, capability, Date.now()));
    return json({ status: await repository.cancel(sessionId, capability, Date.now()) });
  }

  const assets = (env as unknown as { ASSETS?: Fetcher }).ASSETS;
  return assets ? assets.fetch(request) : new Response('Not found', { status: 404, headers: securityHeaders });
};

export default {
  fetch: handleRequest,
  async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
    await new D1SessionRepository(env.OAUTH_SESSIONS, env.SESSION_ENCRYPTION_KEY).deleteExpired(Date.now());
  },
} satisfies ExportedHandler<Env>;
