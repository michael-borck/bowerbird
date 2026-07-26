import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app, BrowserWindow } from 'electron';

const dirname = path.dirname(fileURLToPath(import.meta.url));

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
    },
  });
  void win.loadFile(path.join(dirname, 'web/index.html'));
}

app.whenReady().then(async () => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
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
