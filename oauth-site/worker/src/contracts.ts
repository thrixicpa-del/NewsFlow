export const SESSION_TTL_MS = 10 * 60 * 1000;
export const CALLBACK_PATH = '/oauth/youtube/callback';
export const API_PREFIX = '/oauth/youtube';

export const allowedScopes = (includeMonetary: boolean): string[] => [
  'openid',
  'email',
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

export type SessionStatus = 'pending' | 'ready' | 'denied' | 'cancelled' | 'consumed';

export interface OAuthSessionRecord {
  id: string;
  stateHash: string;
  pollCapabilityHash: string;
  profileId: string;
  includeMonetary: boolean;
  codeVerifierEncrypted: string;
  credentialsEncrypted: string | null;
  status: SessionStatus;
  diagnosticId: string;
  expiresAt: number;
  createdAt: number;
}

export interface CreateSessionResponse {
  sessionId: string;
  pollCapability: string;
  authorizationUrl: string;
  expiresAt: string;
}

export type SessionResult =
  | { status: 'pending'; expiresAt: string }
  | { status: 'denied' | 'expired' | 'cancelled' | 'consumed'; diagnosticId: string }
  | { status: 'ready'; credentials: Record<string, unknown> };
