/* Familienhub – Service Worker nur für Web Push (kein Offline-Cache; den macht die App selbst).
   Nachricht vom Server (notify.py): {title, body, data: {route?, reminder_id?, actions?, action_token?}, category} */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// Base URL of the app (scope of this worker): '/' normally, '/api/hassio_ingress/<token>/' under HA ingress
const BASE = new URL('./', self.location).href;

const ACTION_TITLES = { done: 'Erledigt', snooze_1h: 'In 1 Std.', tomorrow: 'Morgen' };

self.addEventListener('push', (event) => {
  let msg = {};
  try { msg = event.data ? event.data.json() : {}; } catch (_) { msg = { body: event.data && event.data.text() }; }
  const data = msg.data || {};
  const title = msg.title || 'Familienhub';
  // Knöpfe (Erinnerungen); Chrome zeigt höchstens zwei, Safari/iOS gar keine
  const actions = String(data.actions || '').split(',').filter((a) => ACTION_TITLES[a]).slice(0, 2)
    .map((a) => ({ action: a, title: ACTION_TITLES[a] }));
  event.waitUntil(self.registration.showNotification(title, {
    body: msg.body || '',
    icon: BASE + 'icons/Icon-192.png',
    badge: BASE + 'icons/Icon-192.png',
    actions,
    data: { route: data.route || '/', reminder_id: data.reminder_id, action_token: data.action_token },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const d = event.notification.data || {};
  if (event.action && d.reminder_id && d.action_token) {
    // Knopf: Aktion direkt ausführen, ohne die App zu öffnen
    event.waitUntil(fetch(BASE + 'api/reminders/' + d.reminder_id + '/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: event.action, token: d.action_token }),
    }).catch(() => {}));
    return;
  }
  const route = d.route || '/';  // route inside the app, not a URL path
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of all) {
      if (new URL(client.url).origin === self.location.origin) {
        client.postMessage({ route });
        return client.focus();
      }
    }
    return self.clients.openWindow(BASE + '?route=' + encodeURIComponent(route));
  })());
});
