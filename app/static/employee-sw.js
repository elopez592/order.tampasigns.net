// Only the public app shell is cached. Never cache staff APIs, files, or sessions.
const CACHE = 'tampa-signs-employee-shell-20260930-1';
const SHELL = ['/staff/app', '/static/employee.css?v=20260930-1', '/static/employee.js?v=20260930-1',
  '/static/employee-drafts.js?v=20260930-1', '/static/employee.webmanifest',
  '/static/employee-icon-192.png', '/static/employee-icon-512.png', '/static/brand/tampa-black.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('tampa-signs-employee-shell-') && key !== CACHE)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname === '/staff/app') {
    event.respondWith(fetch(event.request).then(response => {
      if (!response.ok) return caches.match('/staff/app').then(cached => cached || response);
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put('/staff/app', copy)));
      return response;
    }).catch(() => caches.match('/staff/app')));
  } else if (SHELL.includes(url.pathname + url.search) || SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
