export async function api(path, { method = 'GET', body } = {}) {
	const res = await fetch('/api' + path, {
		method,
		headers: body ? { 'content-type': 'application/json' } : {},
		body: body && JSON.stringify(body)
	});
	const data = await res.json().catch(() => ({}));
	if (!res.ok) {
		const msg = typeof data.detail === 'string' ? data.detail : 'Ошибка сервера';
		throw Object.assign(new Error(msg), { status: res.status });
	}
	return data;
}
