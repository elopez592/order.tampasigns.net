// Only the public app shell is cached. Never cache staff APIs, files, or sessions.
const CACHE = 'tampa-signs-employee-shell-20261005-1';
const SHELL = ['/staff/app', '/static/employee.css?v=20260930-2', '/static/employee.js?v=20261005-1',
  '/static/employee-drafts.js?v=20260930-2', '/static/survey-review.js?v=20261005-1', '/staff/manifest.webmanifest', '/static/company-brand.js?v=2', '/brand/theme.css',
  '/brand/app-icon.png', '/static/brand/tampa-black.png'];
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
  if (['/staff/app','/staff/manifest.webmanifest','/brand/theme.css','/brand/app-icon.png'].includes(url.pathname)) {
    event.respondWith(fetch(event.request).then(response => {
      if (response.status===403) {event.waitUntil(caches.delete(CACHE));return response;}
      if (!response.ok) return response;
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy)));
      return response;
    }).catch(() => caches.match(event.request)));
  } else if (SHELL.includes(url.pathname + url.search) || SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
