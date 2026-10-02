import { api } from '#lib/api.js';

export const pushSupported = () =>
	typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

function keyBytes(base64url) {
	const s = atob(base64url.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (base64url.length % 4)) % 4));
	return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

// Подписаться и сообщить серверу. Повторный вызов безопасен: сервер обновит владельца подписки.
export async function subscribe(vapidKey) {
	const reg = await navigator.serviceWorker.ready;
	const sub =
		(await reg.pushManager.getSubscription()) ??
		(await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(vapidKey) }));
	const { endpoint, keys } = sub.toJSON();
	await api('/push/subscribe', { method: 'POST', body: { endpoint, keys } });
}
