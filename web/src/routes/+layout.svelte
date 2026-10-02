<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';

	let { children } = $props();
	let waiting = $state(0);

	onMount(async () => {
		if (page.url.pathname === '/login') return;
		try {
			session.me = await api('/me');
		} catch {
			goto('/login', { replaceState: true });
		}
	});

	// Счётчик того, что ждёт действия: супруге — подписи, супругу — возвраты и упразднения на его подписи.
	$effect(() => {
		if (!session.me) return;
		page.url.pathname; // пересчитывать при переходах
		const status = session.me.role === 'wife' ? 'pending,partial' : 'returned';
		api('/bills?status=' + status)
			.then((list) => (waiting = list.length))
			.catch(() => {});
	});

	async function logout() {
		await api('/auth/logout', { method: 'POST' });
		session.me = null;
		goto('/login', { replaceState: true });
	}

	const here = (path) => (path === '/' ? page.url.pathname === '/' || page.url.pathname.startsWith('/laws') : page.url.pathname.startsWith(path));
</script>

{#if session.me && page.url.pathname !== '/login'}
	<nav>
		<a href="/" class:on={here('/')}>Пакт</a>
		<a href="/bills" class:on={here('/bills')}>
			Законопроекты{#if waiting}<span class="badge">{waiting}</span>{/if}
		</a>
		<button class="link" onclick={logout}>Выйти</button>
	</nav>
{/if}

<main>
	{#if session.me || page.url.pathname === '/login'}
		{@render children()}
	{/if}
</main>

<style>
	:global(:root) {
		--paper: #f6f1e7;
		--ink: #1f1c17;
		--muted: #6f675a;
		--line: #d9cfbd;
		--seal: #8a1c1c;
		--field: #fffdf8;
		--ok: #2f5d3a;
		color-scheme: light;
	}
	@media (prefers-color-scheme: dark) {
		:global(:root) {
			--paper: #1a1814;
			--ink: #ece5d6;
			--muted: #a59c8b;
			--line: #3a352c;
			--seal: #d9675f;
			--field: #24211b;
			--ok: #8fc29a;
			color-scheme: dark;
		}
	}
	:global(*) {
		box-sizing: border-box;
	}
	:global(body) {
		margin: 0;
		background: var(--paper);
		color: var(--ink);
		font: 17px/1.5 Georgia, 'Times New Roman', serif;
		-webkit-tap-highlight-color: transparent;
	}
	:global(a) {
		color: inherit;
	}
	:global(button, input, textarea, select) {
		font: inherit;
		color: inherit;
	}
	:global(button) {
		min-height: 44px;
		padding: 0 18px;
		border: 1px solid var(--ink);
		border-radius: 2px;
		background: var(--ink);
		color: var(--paper);
		cursor: pointer;
	}
	:global(button.quiet) {
		background: transparent;
		color: var(--ink);
		border-color: var(--line);
	}
	:global(button.link) {
		min-height: 0;
		padding: 0;
		border: 0;
		background: none;
		color: var(--muted);
		text-decoration: underline;
		text-underline-offset: 3px;
	}
	:global(button:disabled) {
		opacity: 0.5;
	}
	:global(input, textarea, select) {
		width: 100%;
		min-height: 44px;
		padding: 8px 12px;
		border: 1px solid var(--line);
		border-radius: 2px;
		background: var(--field);
		color: var(--ink);
		font-size: 17px;
	}
	:global(textarea) {
		min-height: 96px;
		resize: vertical;
	}
	:global(input:focus, textarea:focus, select:focus) {
		outline: 2px solid var(--ink);
		outline-offset: -1px;
	}
	:global(label) {
		display: grid;
		gap: 4px;
		color: var(--muted);
		font-size: 15px;
	}
	:global(h1, h2, h3) {
		font-weight: normal;
	}
	:global(.num) {
		color: var(--seal);
		font-variant-numeric: tabular-nums;
	}
	:global(.muted) {
		color: var(--muted);
	}
	:global(.error) {
		color: var(--seal);
	}
	:global(.actions) {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		margin-top: 24px;
	}
	nav {
		position: sticky;
		top: 0;
		z-index: 1;
		display: flex;
		align-items: center;
		gap: 20px;
		max-width: 640px;
		margin: 0 auto;
		padding: max(12px, env(safe-area-inset-top)) 16px 12px;
		background: var(--paper);
		border-bottom: 1px solid var(--line);
	}
	nav a {
		text-decoration: none;
		color: var(--muted);
		letter-spacing: 0.04em;
	}
	nav a.on {
		color: var(--ink);
	}
	nav .link {
		margin-left: auto;
	}
	.badge {
		display: inline-block;
		min-width: 20px;
		margin-left: 6px;
		padding: 0 6px;
		border-radius: 10px;
		background: var(--seal);
		color: var(--paper);
		font-size: 13px;
		line-height: 20px;
		text-align: center;
	}
	main {
		max-width: 640px;
		margin: 0 auto;
		padding: 24px 16px 48px;
	}
</style>
