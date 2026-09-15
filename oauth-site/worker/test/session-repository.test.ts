import { describe, expect, it } from 'vitest';
import { InMemorySessionRepository } from '../src/session-repository';

describe('one-time OAuth session repository', () => {
  it('returns credentials once and reports consumed on replay', async () => {
    const repository = new InMemorySessionRepository();
    await repository.create({
      id: 'session-a', state: 'state-a', pollCapability: 'capability-a', profileId: 'profile-a',
      includeMonetary: false, codeVerifierEncrypted: 'encrypted-verifier', diagnosticId: 'diag-a',
      createdAt: 1000, expiresAt: 601000,
    });
    await repository.markReady('session-a', 'encrypted-credentials');

    expect((await repository.consume('session-a', 'capability-a', 1001)).status).toBe('ready');
    expect((await repository.consume('session-a', 'capability-a', 1001)).status).toBe('consumed');
  });
});
