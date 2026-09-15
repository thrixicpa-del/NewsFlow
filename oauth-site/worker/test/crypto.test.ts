import { describe, expect, it } from 'vitest';
import { decryptJson, encryptJson } from '../src/crypto';

const key = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

describe('temporary OAuth credential encryption', () => {
  it('round-trips encrypted JSON without putting its plaintext in the ciphertext', async () => {
    const encrypted = await encryptJson({ refresh_token: 'refresh-secret' }, key);

    expect(encrypted).not.toContain('refresh-secret');
    await expect(decryptJson<{ refresh_token: string }>(encrypted, key))
      .resolves.toEqual({ refresh_token: 'refresh-secret' });
  });
});
