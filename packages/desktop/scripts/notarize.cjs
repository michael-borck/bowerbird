const { notarize } = require('@electron/notarize');
const { execFileSync } = require('child_process');

// electron-builder loads hooks via `require(path).default`. Using
// `module.exports = fn` would silently no-op. (Pattern from cite-sight.)
exports.default = async function notarizing(context) {
  const { electronPlatformName, appOutDir } = context;
  console.log(`[notarize] afterSign hook entered (platform=${electronPlatformName})`);
  if (electronPlatformName !== 'darwin') return;

  // Renamed from APPLE_* so electron-builder's auto-detection doesn't also
  // fire its own (broken) notarize wrapper alongside ours.
  const appleId = process.env.NOTARIZE_APPLE_ID;
  const appleIdPassword = process.env.NOTARIZE_APPLE_PASSWORD;
  const teamId = process.env.NOTARIZE_APPLE_TEAM_ID;
  if (!appleId || !appleIdPassword || !teamId) {
    console.log('[notarize] Skipping — NOTARIZE_APPLE_* credentials not all set');
    return;
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = `${appOutDir}/${appName}.app`;
  const appBundleId = context.packager.appInfo.id;

  console.log(`[notarize] Notarizing ${appPath} (bundleId=${appBundleId}, teamId=${teamId})`);
  await notarize({
    tool: 'notarytool',
    appBundleId,
    appPath,
    appleId,
    appleIdPassword,
    teamId,
  });

  // @electron/notarize only submits + polls; stapling embeds the ticket so
  // Gatekeeper can verify offline. Non-fatal if it fails — the app is still
  // notarised, just not stapled.
  console.log('[notarize] Stapling ticket');
  try {
    execFileSync('xcrun', ['stapler', 'staple', appPath], { stdio: 'inherit' });
    console.log('[notarize] Stapled');
  } catch (err) {
    console.warn(`[notarize] Staple failed (build will continue): ${err.message}`);
  }
};
