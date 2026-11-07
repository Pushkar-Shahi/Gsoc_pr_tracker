// Service Worker Registration & PWA Install Manager

let deferredPrompt: any = null;

export function registerServiceWorker() {
  if (typeof window === 'undefined') return;

  // Auto-reload once if Vite encounters a missing hashed chunk from an updated deployment
  window.addEventListener('vite:preloadError', () => {
    console.warn('[PWA] Stale chunk detected after deployment update, reloading fresh bundle...');
    window.location.reload();
  });

  if ('serviceWorker' in navigator) {
    // In local development on localhost, unregister service workers to avoid stale assets
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        for (const registration of registrations) {
          registration.unregister();
        }
      });
      if ('caches' in window) {
        caches.keys().then((keys) => {
          for (const key of keys) {
            caches.delete(key);
          }
        });
      }
      return;
    }

    // Auto-reload as soon as an updated Service Worker takes control
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!refreshing) {
        refreshing = true;
        console.log('[PWA] New controller active. Reloading to apply update...');
        window.location.reload();
      }
    });

    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .then((registration) => {
          // Check for service worker updates immediately on every page load
          registration.update().catch(() => {});

          // Listen for new worker installation and activate immediately
          registration.onupdatefound = () => {
            const installing = registration.installing;
            if (installing) {
              installing.onstatechange = () => {
                if (installing.state === 'installed' && navigator.serviceWorker.controller) {
                  console.log('[PWA] New version ready. Reloading for instant update...');
                  if (!refreshing) {
                    refreshing = true;
                    window.location.reload();
                  }
                }
              };
            }
          };
        })
        .catch((error) => {
          console.warn('[PWA] ServiceWorker registration failed:', error);
        });
    });
  }

  // Capture beforeinstallprompt for in-app install button
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    window.dispatchEvent(new CustomEvent('pwa-installable', { detail: true }));
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    window.dispatchEvent(new CustomEvent('pwa-installed'));
    console.log('[PWA] Application installed on device!');
  });
}

export async function promptPWAInstall(): Promise<boolean> {
  if (!deferredPrompt) {
    return false;
  }
  deferredPrompt.prompt();
  const choiceResult = await deferredPrompt.userChoice;
  deferredPrompt = null;
  return choiceResult.outcome === 'accepted';
}
