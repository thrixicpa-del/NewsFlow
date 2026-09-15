const encoder = new TextEncoder();
const decoder = new TextDecoder();

const toBase64Url = (bytes: Uint8Array): string => {
  let text = '';
  bytes.forEach((value) => { text += String.fromCharCode(value); });
  return btoa(text).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
};

const fromBase64Url = (value: string): Uint8Array => {
  const padded = value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - value.length % 4) % 4);
  const text = atob(padded);
  return Uint8Array.from(text, (character) => character.charCodeAt(0));
};

const toArrayBuffer = (value: Uint8Array): ArrayBuffer => value.buffer.slice(
  value.byteOffset, value.byteOffset + value.byteLength,
) as ArrayBuffer;

const encryptionKey = async (encodedKey: string): Promise<CryptoKey> => crypto.subtle.importKey(
  'raw', toArrayBuffer(fromBase64Url(encodedKey)), { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'],
);

export const sha256Base64Url = async (value: string): Promise<string> => toBase64Url(
  new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value))),
);

export const encryptJson = async (value: unknown, encodedKey: string): Promise<string> => {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv }, await encryptionKey(encodedKey), encoder.encode(JSON.stringify(value)),
  );
  return JSON.stringify({ v: 1, iv: toBase64Url(iv), ciphertext: toBase64Url(new Uint8Array(ciphertext)) });
};

export const decryptJson = async <T>(ciphertext: string, encodedKey: string): Promise<T> => {
  const value: unknown = JSON.parse(ciphertext);
  if (!value || typeof value !== 'object') throw new Error('Invalid encrypted session payload');
  const record = value as { v?: unknown; iv?: unknown; ciphertext?: unknown };
  if (record.v !== 1 || typeof record.iv !== 'string' || typeof record.ciphertext !== 'string') {
    throw new Error('Invalid encrypted session payload');
  }
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: toArrayBuffer(fromBase64Url(record.iv)) },
    await encryptionKey(encodedKey),
    toArrayBuffer(fromBase64Url(record.ciphertext)),
  );
  return JSON.parse(decoder.decode(plaintext)) as T;
};
