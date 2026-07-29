import path from 'node:path';
import type { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';
import { app, BrowserWindow } from 'electron';
import { suggestResources, configFromEnv } from '@michaelborck/bowerbird-core';
import { createApp } from '@michaelborck/bowerbird-server';

const dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * The desktop app is the same web UI served by the same HTTP contract,
 * embedded (ADR-0010). Requests run inline — no queue on a personal
 * machine — and user credentials come per request from the UI's settings
 * panel (browser storage, ADR-0004). Loopback only: nothing on the LAN
 * can reach this server.
 */
/**
 * ADR-0005 layer 3: full-page screenshots via Electron's own Chromium —
 * the reason the desktop tier needs no separate browser download
 * (ADR-0010). Hidden window, hard timeout, and failure returns undefined:
 * screenshots are triage bonus, never a blocker.
 */
async function captureScreenshot(url: string): Promise<string | undefined> {
  const win = new BrowserWindow({
    show: false,
    width: 1024,
    height: 768,
    webPreferences: { sandbox: true, contextIsolation: true },
  });
  try {
    await Promise.race([
      win.loadURL(url),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('screenshot timeout')), 15_000),
      ),
    ]);
    // Give late-painting pages a beat before capturing.
    await new Promise((r) => setTimeout(r, 800));
    const image = await win.webContents.capturePage();
    return image.resize({ width: 480 }).toDataURL();
  } catch {
    return undefined;
  } finally {
    win.destroy();
  }
}

function startEmbeddedServer(): Promise<number> {
  const server = createApp({
    pipelineDefaults: configFromEnv(),
    run: (job, config) => suggestResources(job, config),
    queueAvailable: false,
    webDistPath: path.join(dirname, 'web'),
    version: app.getVersion(),
    allowBatch: true,
    screenshot: captureScreenshot,
  });
  return new Promise((resolve, reject) => {
    const listener = server.listen(0, '127.0.0.1', () => {
      const { port } = listener.address() as AddressInfo;
      console.log(`bowerbird desktop server on 127.0.0.1:${port}`);
      resolve(port);
    });
    listener.on('error', reject);
  });
}

function createWindow(port: number): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
    },
  });
  void win.loadURL(`http://127.0.0.1:${port}`);
}

app.whenReady().then(async () => {
  const port = await startEmbeddedServer();
  createWindow(port);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(port);
  });

  // Auto-update against GitHub Releases; non-fatal if offline (ADR-0006).
  // electron-updater is CJS, so its exports sit under `.default` when
  // dynamically imported from ESM.
  if (app.isPackaged) {
    try {
      const updater = await import('electron-updater');
      const { autoUpdater } = (updater.default ?? updater) as typeof updater;
      await autoUpdater.checkForUpdatesAndNotify();
    } catch (error) {
      console.warn('Auto-update check failed:', error);
    }
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
