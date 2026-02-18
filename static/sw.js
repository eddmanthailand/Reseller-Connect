const CACHE_NAME = 'ekg-shops-v15';
const STATIC_ASSETS = [
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/static/') && !url.pathname.endsWith('.js') && !url.pathname.endsWith('.css')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});

self.addEventListener('push', (event) => {
  let data = { title: 'EKG Shops', body: 'มีการแจ้งเตือนใหม่', icon: '/static/icons/icon-192x192.png' };

  if (event.data) {
    try {
      data = Object.assign(data, event.data.json());
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/',
      type: data.type || 'general'
    },
    actions: data.actions || [],
    tag: data.tag || 'ekg-notification',
    renotify: true
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const urlToOpen = event.notification.data.url || '/';
  const fullUrl = new URL(urlToOpen, self.location.origin).href;
  const targetPath = new URL(fullUrl).pathname;
  const targetHash = new URL(fullUrl).hash || '';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      let matchingClient = null;
      let anyClient = null;

      for (const client of windowClients) {
        if (!client.url.includes(self.location.origin) || !('focus' in client)) continue;
        const clientPath = new URL(client.url).pathname;
        if (clientPath === targetPath) {
          matchingClient = client;
          break;
        }
        if (!anyClient) anyClient = client;
      }

      if (matchingClient) {
        matchingClient.postMessage({
          type: 'NOTIFICATION_CLICK',
          url: fullUrl,
          hash: targetHash,
          notificationData: event.notification.data
        });
        return matchingClient.focus();
      }

      if (anyClient) {
        const anyClientPath = new URL(anyClient.url).pathname;
        if (anyClientPath === targetPath) {
          anyClient.postMessage({
            type: 'NOTIFICATION_CLICK',
            url: fullUrl,
            hash: targetHash,
            notificationData: event.notification.data
          });
          return anyClient.focus();
        }
      }

      return clients.openWindow(fullUrl);
    })
  );
});
