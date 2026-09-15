import * as oauth from 'oauth4webapi';
import { CALLBACK_PATH, allowedScopes } from './contracts';

const GOOGLE_AUTHORIZATION_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth';

export interface GoogleAuthorizationInput {
  clientId: string;
  serviceOrigin: string;
  state: string;
  codeVerifier: string;
  includeMonetary: boolean;
}

export const createGoogleAuthorizationUrl = async (input: GoogleAuthorizationInput): Promise<string> => {
  const origin = new URL(input.serviceOrigin);
  if (origin.protocol !== 'https:') throw new Error('OAuth service must use HTTPS');
  const url = new URL(GOOGLE_AUTHORIZATION_ENDPOINT);
  url.searchParams.set('client_id', input.clientId);
  url.searchParams.set('redirect_uri', new URL(CALLBACK_PATH, origin).toString());
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('scope', allowedScopes(input.includeMonetary).join(' '));
  url.searchParams.set('state', input.state);
  url.searchParams.set('access_type', 'offline');
  url.searchParams.set('prompt', 'consent');
  url.searchParams.set('code_challenge_method', 'S256');
  url.searchParams.set('code_challenge', await oauth.calculatePKCECodeChallenge(input.codeVerifier));
  return url.toString();
};

export interface GoogleTokenExchangeInput {
  clientId: string;
  clientSecret: string;
  serviceOrigin: string;
  code: string;
  codeVerifier: string;
}

export const exchangeGoogleAuthorizationCode = async (input: GoogleTokenExchangeInput): Promise<Record<string, unknown>> => {
  const redirectUri = new URL(CALLBACK_PATH, new URL(input.serviceOrigin)).toString();
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code: input.code,
      client_id: input.clientId,
      client_secret: input.clientSecret,
      redirect_uri: redirectUri,
      grant_type: 'authorization_code',
      code_verifier: input.codeVerifier,
    }),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok || !payload || typeof payload !== 'object') throw new Error('Google token exchange failed');
  const token = payload as Record<string, unknown>;
  if (typeof token.access_token !== 'string' || !token.access_token || typeof token.refresh_token !== 'string' || !token.refresh_token) {
    throw new Error('Google did not return a reusable channel credential');
  }
  // The desktop uses google-auth's authorized-user format. Google returns a
  // web token response instead, so retain the local refresh metadata needed
  // to use and later refresh that credential.
  const expiresIn = typeof token.expires_in === 'number' ? token.expires_in : Number(token.expires_in);
  const scope = typeof token.scope === 'string' ? token.scope.split(' ').filter(Boolean) : [];
  return {
    token: token.access_token,
    refresh_token: token.refresh_token,
    token_uri: 'https://oauth2.googleapis.com/token',
    client_id: input.clientId,
    client_secret: input.clientSecret,
    scopes: scope,
    ...(Number.isFinite(expiresIn) && expiresIn > 0 ? { expiry: new Date(Date.now() + expiresIn * 1000).toISOString() } : {}),
  };
};
