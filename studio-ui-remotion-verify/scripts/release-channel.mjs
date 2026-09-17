const policies = {
  DEV: {
    name: "DEV",
    purpose: "Developer-only local iteration.",
    requiresImmutableArtifact: false,
    requiresReleaseGate: false,
    requiresManualAcceptance: false,
    allowsAutoUpdate: false,
  },
  TEST: {
    name: "TEST",
    purpose: "Disposable automated and manual validation.",
    requiresImmutableArtifact: true,
    requiresReleaseGate: false,
    requiresManualAcceptance: false,
    allowsAutoUpdate: false,
  },
  RC: {
    name: "RC",
    purpose: "Candidate distributed only after the authoritative release gate.",
    requiresImmutableArtifact: true,
    requiresReleaseGate: true,
    requiresManualAcceptance: false,
    allowsAutoUpdate: false,
  },
  STABLE: {
    name: "STABLE",
    purpose: "Accepted production release; auto-update remains intentionally deferred.",
    requiresImmutableArtifact: true,
    requiresReleaseGate: true,
    requiresManualAcceptance: true,
    allowsAutoUpdate: false,
  },
};

export const RELEASE_CHANNELS = Object.freeze(policies);

export function releaseChannel(value) {
  const normalized = String(value || "").trim().toUpperCase();
  const policy = RELEASE_CHANNELS[normalized];
  if (!policy) throw new Error("Release channel must be DEV, TEST, RC, or STABLE");
  return policy;
}
