import { afterEach, describe, expect, it, vi } from 'vitest';
import { createGoogleAuthorizationUrl, exchangeGoogleAuthorizationCode } from '../src/google-oauth';

describe('Google OAuth client request', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uses a fixed HTTPS callback, PKCE, and no monetary scope by default', async () => {
    const authorizationUrl = await createGoogleAuthorizationUrl({
      clientId: 'client-id.apps.googleusercontent.com',
      serviceOrigin: 'https://a.tinkbro.online',
      state: 'state-a',
      codeVerifier: 'A'.repeat(64),
      includeMonetary: false,
    });
    const url = new URL(authorizationUrl);

    expect(url.origin).toBe('https://accounts.google.com');
    expect(url.pathname).toBe('/o/oauth2/v2/auth');
    expect(url.searchParams.get('redirect_uri')).toBe('https://a.tinkbro.online/oauth/youtube/callback');
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(url.searchParams.get('scope')).not.toContain('yt-analytics-monetary');
  });

  it('returns a desktop-compatible credential payload after the code exchange', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: 'access-token', refresh_token: 'refresh-token', expires_in: 3600, scope: 'scope-a', token_type: 'Bearer',
    }), { status: 200, headers: { 'content-type': 'application/json' } })));

    const credentials = await exchangeGoogleAuthorizationCode({
      clientId: 'client-id.apps.googleusercontent.com', clientSecret: 'client-secret',
      serviceOrigin: 'https://a.tinkbro.online', code: 'code-a', codeVerifier: 'A'.repeat(64),
    });

    expect(credentials).toMatchObject({
      token: 'access-token', refresh_token: 'refresh-token', client_id: 'client-id.apps.googleusercontent.com', client_secret: 'client-secret',
    });
  });
});
