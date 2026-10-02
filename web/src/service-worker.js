/// <reference lib="webworker" />
// Service worker: push-уведомления с кнопками и офлайн-чтение Пакта.
import { assets, immutable } from '$app/manifest';
import { version } from '$app/env';

const CACHE = `pact-${version}`;
const abs = (p) => new URL(p, self.registration.scope).href;
const SHELL = [abs('/'), ...immutable.map((f) => abs(f.path)), ...assets.map((f) => abs(f.path))];
// Что читается офлайн: дерево, законы и текущий пользователь (без него не отрисуется оболочка).
const READABLE = /^\/api\/(pakt|laws\/\d+|me)$/;

self.addEventListener('install', (e) => {
	e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
	e.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

async function networkFirst(request, fallback = request) {
	const cache = await caches.open(CACHE);
	try {
		const res = await fetch(request);
		if (res.ok) cache.put(fallback, res.clone());
		return res;
	} catch (err) {
		const hit = await cache.match(fallback);
		if (hit) return hit;
		throw err;
	}
}

self.addEventListener('fetch', (e) => {
	const { request } = e;
	const url = new URL(request.url);
	if (request.method !== 'GET' || url.origin !== self.location.origin) return;
	if (READABLE.test(url.pathname)) return e.respondWith(networkFirst(request));
	if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/calendar/')) return;
	// Любая страница SPA — это index.html.
	if (request.mode === 'navigate') return e.respondWith(networkFirst(request, abs('/')));
	if (url.pathname.startsWith('/_app/immutable/')) {
		e.respondWith(caches.match(request).then((hit) => hit ?? fetch(request)));
	}
});

self.addEventListener('push', (e) => {
	const d = e.data?.json() ?? {};
	e.waitUntil(
		self.registration.showNotification(d.title ?? 'Пакт', {
			body: d.body,
			tag: d.tag,
			data: d,
			actions: d.actions ?? [],
			icon: '/icon-192.png',
			badge: '/icon-192.png'
		})
	);
});

self.addEventListener('notificationclick', (e) => {
	const d = e.notification.data ?? {};
	e.notification.close();
	if (e.action === 'done' || e.action === 'snooze') {
		e.waitUntil(
			fetch(`/api/laws/${d.law_id}/${e.action}`, { method: 'POST', credentials: 'same-origin' }).then((r) => {
				if (!r.ok) return self.registration.showNotification('Не удалось отметить', { body: 'Откройте Пакт и войдите заново.' });
			})
		);
		return;
	}
	e.waitUntil(
		self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
			const win = list.find((c) => 'focus' in c);
			if (win) return win.navigate(d.url ?? '/').then((w) => (w ?? win).focus());
			return self.clients.openWindow(d.url ?? '/');
		})
	);
});
