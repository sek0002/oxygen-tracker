const CACHE = 'oxygen-shell-v26';
const ASSETS = ['./', './index.html', './styles.css', './app.js', './model.js', './store.js', './config.js', './pwa.js', './theme.js', './favicon.svg', './manifest.webmanifest', './icon-180.png', './icon-192.png', './icon-512.png'];
const urls = new Set(ASSETS.map(path => new URL(path, self.registration.scope).href));
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('oxygen-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  // Cache the public app shell only. Authentication, readings and exports stay online-only.
  if (event.request.method !== 'GET' || !urls.has(event.request.url)) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy)));
    }
    return response;
  }).catch(async () => (await caches.match(event.request)) || Response.error()));
});
