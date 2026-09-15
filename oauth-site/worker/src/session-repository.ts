import type { OAuthSessionRecord, SessionResult, SessionStatus } from './contracts';
import { decryptJson, sha256Base64Url } from './crypto';

export interface PendingSession {
  id: string;
  state: string;
  pollCapability: string;
  profileId: string;
  includeMonetary: boolean;
  codeVerifierEncrypted: string;
  diagnosticId: string;
  createdAt: number;
  expiresAt: number;
}

export class InMemorySessionRepository {
  private readonly sessions = new Map<string, OAuthSessionRecord>();

  async create(input: PendingSession): Promise<void> {
    this.sessions.set(input.id, {
      id: input.id,
      stateHash: await sha256Base64Url(input.state),
      pollCapabilityHash: await sha256Base64Url(input.pollCapability),
      profileId: input.profileId,
      includeMonetary: input.includeMonetary,
      codeVerifierEncrypted: input.codeVerifierEncrypted,
      credentialsEncrypted: null,
      status: 'pending',
      diagnosticId: input.diagnosticId,
      expiresAt: input.expiresAt,
      createdAt: input.createdAt,
    });
  }

  async markReady(id: string, credentialsEncrypted: string): Promise<boolean> {
    const session = this.sessions.get(id);
    if (!session || session.status !== 'pending') return false;
    session.credentialsEncrypted = credentialsEncrypted;
    session.status = 'ready';
    return true;
  }

  async consume(id: string, pollCapability: string, now: number): Promise<SessionResult> {
    const session = this.sessions.get(id);
    if (!session || session.status === 'consumed') return { status: 'consumed', diagnosticId: '' };
    if (session.expiresAt <= now) {
      this.sessions.delete(id);
      return { status: 'expired', diagnosticId: session.diagnosticId };
    }
    if (session.pollCapabilityHash !== await sha256Base64Url(pollCapability)) return { status: 'consumed', diagnosticId: '' };
    if (session.status === 'pending') return { status: 'pending', expiresAt: new Date(session.expiresAt).toISOString() };
    if (session.status === 'denied' || session.status === 'cancelled') return { status: session.status, diagnosticId: session.diagnosticId };
    if (session.status !== 'ready') return { status: 'consumed', diagnosticId: '' };
    session.status = 'consumed';
    return { status: 'ready', credentials: {} };
  }

  async setStatus(id: string, status: Extract<SessionStatus, 'denied' | 'cancelled'>): Promise<void> {
    const session = this.sessions.get(id);
    if (session && session.status === 'pending') session.status = status;
  }
}

const asRecord = (row: Record<string, unknown>): OAuthSessionRecord => ({
  id: String(row.id),
  stateHash: String(row.state_hash),
  pollCapabilityHash: String(row.poll_capability_hash),
  profileId: String(row.profile_id),
  includeMonetary: Boolean(row.include_monetary),
  codeVerifierEncrypted: String(row.code_verifier_encrypted),
  credentialsEncrypted: typeof row.credentials_encrypted === 'string' ? row.credentials_encrypted : null,
  status: String(row.status) as SessionStatus,
  diagnosticId: String(row.diagnostic_id),
  expiresAt: Number(row.expires_at),
  createdAt: Number(row.created_at),
});

export class D1SessionRepository {
  constructor(private readonly database: D1Database, private readonly encryptionKey: string) {}

  async create(input: PendingSession): Promise<void> {
    await this.database.prepare(`INSERT INTO oauth_sessions (
      id, state_hash, poll_capability_hash, profile_id, include_monetary,
      code_verifier_encrypted, credentials_encrypted, status, diagnostic_id, expires_at, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?, ?)`)
      .bind(input.id, await sha256Base64Url(input.state), await sha256Base64Url(input.pollCapability), input.profileId,
        input.includeMonetary ? 1 : 0, input.codeVerifierEncrypted, input.diagnosticId, input.expiresAt, input.createdAt)
      .run();
  }

  async findByState(state: string, now: number): Promise<OAuthSessionRecord | null> {
    const row = await this.database.prepare(
      `SELECT * FROM oauth_sessions WHERE state_hash = ? AND status = 'pending' AND expires_at > ? LIMIT 1`,
    ).bind(await sha256Base64Url(state), now).first<Record<string, unknown>>();
    return row ? asRecord(row) : null;
  }

  async markReady(id: string, credentialsEncrypted: string): Promise<boolean> {
    const result = await this.database.prepare(
      `UPDATE oauth_sessions SET status = 'ready', credentials_encrypted = ?, code_verifier_encrypted = ''
       WHERE id = ? AND status = 'pending'`,
    ).bind(credentialsEncrypted, id).run();
    return (result.meta.changes || 0) === 1;
  }

  async markDenied(id: string, diagnosticId: string): Promise<void> {
    await this.database.prepare(
      `UPDATE oauth_sessions SET status = 'denied', diagnostic_id = ?, code_verifier_encrypted = ''
       WHERE id = ? AND status = 'pending'`,
    ).bind(diagnosticId, id).run();
  }

  async consume(id: string, pollCapability: string, now: number): Promise<SessionResult> {
    const capabilityHash = await sha256Base64Url(pollCapability);
    const removed = await this.database.prepare(
      `DELETE FROM oauth_sessions
       WHERE id = ? AND poll_capability_hash = ? AND status = 'ready' AND expires_at > ?
       RETURNING credentials_encrypted`,
    ).bind(id, capabilityHash, now).first<{ credentials_encrypted: string }>();
    if (removed?.credentials_encrypted) {
      return { status: 'ready', credentials: await decryptJson<Record<string, unknown>>(removed.credentials_encrypted, this.encryptionKey) };
    }
    const row = await this.database.prepare('SELECT status, diagnostic_id, expires_at FROM oauth_sessions WHERE id = ? LIMIT 1')
      .bind(id).first<{ status: SessionStatus; diagnostic_id: string; expires_at: number }>();
    if (!row || row.status === 'consumed' || row.status === 'ready') return { status: 'consumed', diagnosticId: '' };
    if (row.expires_at <= now) {
      await this.database.prepare('DELETE FROM oauth_sessions WHERE id = ?').bind(id).run();
      return { status: 'expired', diagnosticId: row.diagnostic_id };
    }
    if (row.status === 'pending') return { status: 'pending', expiresAt: new Date(row.expires_at).toISOString() };
    return { status: row.status, diagnosticId: row.diagnostic_id };
  }

  async cancel(id: string, pollCapability: string, now: number): Promise<'cancelled' | 'expired' | 'consumed'> {
    const result = await this.database.prepare(
      `DELETE FROM oauth_sessions WHERE id = ? AND poll_capability_hash = ? AND status = 'pending' AND expires_at > ?`,
    ).bind(id, await sha256Base64Url(pollCapability), now).run();
    if ((result.meta.changes || 0) === 1) return 'cancelled';
    const row = await this.database.prepare('SELECT expires_at FROM oauth_sessions WHERE id = ? LIMIT 1').bind(id)
      .first<{ expires_at: number }>();
    if (row && row.expires_at <= now) return 'expired';
    return 'consumed';
  }

  async deleteExpired(now: number): Promise<number> {
    const result = await this.database.prepare('DELETE FROM oauth_sessions WHERE expires_at <= ?').bind(now).run();
    return result.meta.changes || 0;
  }
}
