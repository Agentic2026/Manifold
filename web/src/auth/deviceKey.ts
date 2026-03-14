import { get, set, del } from "idb-keyval";

const DB_PRIVATE_KEY = "h4ckath0n_device_private_key";
const DB_PUBLIC_JWK = "h4ckath0n_device_public_jwk";
const DB_DEVICE_ID = "h4ckath0n_device_id";
const DB_USER_ID = "h4ckath0n_user_id";

export interface DeviceKeyMaterial {
  privateKey: CryptoKey;
  publicJwk: JsonWebKey;
}

export interface DeviceIdentity {
  deviceId: string;
  userId: string;
}

// Caches for in-memory access
let cachedIdentity: DeviceIdentity | null = null;
let identityLoaded = false;
let cachedKeyMaterial: DeviceKeyMaterial | null = null;
let keyMaterialLoaded = false;

export async function ensureDeviceKeyMaterial(): Promise<DeviceKeyMaterial> {
  const existing = await loadDeviceKeyMaterial();
  if (existing) return existing;
  return generateDeviceKeyMaterial();
}

async function loadDeviceKeyMaterial(): Promise<DeviceKeyMaterial | null> {
  if (keyMaterialLoaded) return cachedKeyMaterial;

  const [privateKey, publicJwk] = await Promise.all([
    get<CryptoKey>(DB_PRIVATE_KEY),
    get<JsonWebKey>(DB_PUBLIC_JWK),
  ]);

  if (privateKey && publicJwk) {
    cachedKeyMaterial = { privateKey, publicJwk };
  } else {
    cachedKeyMaterial = null;
  }
  keyMaterialLoaded = true;
  return cachedKeyMaterial;
}

async function generateDeviceKeyMaterial(): Promise<DeviceKeyMaterial> {
  const keyPair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    false, // non-extractable private key
    ["sign", "verify"],
  );
  const publicJwk = await crypto.subtle.exportKey("jwk", keyPair.publicKey);

  await Promise.all([
    set(DB_PRIVATE_KEY, keyPair.privateKey),
    set(DB_PUBLIC_JWK, publicJwk),
  ]);

  cachedKeyMaterial = { privateKey: keyPair.privateKey, publicJwk };
  keyMaterialLoaded = true;
  return cachedKeyMaterial;
}

export async function getPrivateKey(): Promise<CryptoKey | null> {
  const material = await loadDeviceKeyMaterial();
  return material?.privateKey ?? null;
}

export async function getPublicJwk(): Promise<JsonWebKey | null> {
  const material = await loadDeviceKeyMaterial();
  return material?.publicJwk ?? null;
}

export async function getDeviceIdentity(): Promise<DeviceIdentity | null> {
  if (identityLoaded) return cachedIdentity;

  const [deviceId, userId] = await Promise.all([
    get<string>(DB_DEVICE_ID),
    get<string>(DB_USER_ID),
  ]);

  if (deviceId && userId) {
    cachedIdentity = { deviceId, userId };
  } else {
    cachedIdentity = null;
  }
  identityLoaded = true;
  return cachedIdentity;
}

export async function setDeviceIdentity(
  deviceId: string,
  userId: string,
): Promise<void> {
  await Promise.all([
    set(DB_DEVICE_ID, deviceId),
    set(DB_USER_ID, userId),
  ]);
  cachedIdentity = { deviceId, userId };
  identityLoaded = true;
}

export async function clearDeviceKeyMaterial(): Promise<void> {
  await Promise.all([
    del(DB_PRIVATE_KEY),
    del(DB_PUBLIC_JWK),
    del(DB_DEVICE_ID),
    del(DB_USER_ID),
  ]);
  cachedIdentity = null;
  identityLoaded = true;
  cachedKeyMaterial = null;
  keyMaterialLoaded = true;
}

/**
 * Clear only the authorization binding (device_id + user_id) while
 * preserving the device key pair.  Logout should call this instead of
 * {@link clearDeviceKeyMaterial} so the same key identity can be
 * reused on next login.
 */
export async function clearDeviceAuthorization(): Promise<void> {
  await Promise.all([
    del(DB_DEVICE_ID),
    del(DB_USER_ID),
  ]);
  cachedIdentity = null;
  identityLoaded = true;
}
