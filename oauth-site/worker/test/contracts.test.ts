import { describe, expect, it } from 'vitest';
import { SESSION_TTL_MS, allowedScopes } from '../src/contracts';

describe('OAuth handoff contract', () => {
  it('keeps a session alive for exactly ten minutes and omits money by default', () => {
    expect(SESSION_TTL_MS).toBe(10 * 60 * 1000);
    expect(allowedScopes(false)).toEqual([
      'openid',
      'email',
      'https://www.googleapis.com/auth/youtube.upload',
      'https://www.googleapis.com/auth/youtube.readonly',
      'https://www.googleapis.com/auth/yt-analytics.readonly',
    ]);
  });
});
