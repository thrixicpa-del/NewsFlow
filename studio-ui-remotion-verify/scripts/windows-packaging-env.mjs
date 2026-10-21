// Keep the archive codec compatible with the bundled NSIS extractor.
export function windowsPackagingEnvironment(environment, platform = process.platform) {
  return {
    ...environment,
    // New 7za auto-selects ARM64 BCJ filters which the bundled Nsis7z plugin
    // cannot decode. Pin its supported x86 filter without dropping payload files.
    ...(platform === 'win32' ? { ELECTRON_BUILDER_7Z_FILTER: 'BCJ' } : {}),
  };
}
