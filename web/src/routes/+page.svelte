<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '#lib/api.js';

	let me = $state(null);
	let check = $state(null);
	let busy = $state(false);

	onMount(async () => {
		try {
			me = await api('/me');
		} catch {
			goto('/login', { replaceState: true });
		}
	});

	async function verify() {
		busy = true;
		try {
			check = await api('/journal/verify');
		} catch (err) {
			check = { ok: false, reason: err.message };
		} finally {
			busy = false;
		}
	}

	async function logout() {
		await api('/auth/logout', { method: 'POST' });
		goto('/login', { replaceState: true });
	}
</script>

{#if me}
	<header>
		<h1>Пакт</h1>
		<button class="quiet" onclick={logout}>Выйти</button>
	</header>
	<p>{me.name}, законов пока нет.</p>

	{#if me.role === 'husband'}
		<section>
			<button class="quiet" onclick={verify} disabled={busy}>Проверить журнал</button>
			{#if check}
				<p class:bad={!check.ok}>
					{#if check.ok}
						Цепочка цела: {check.count} записей.
					{:else}
						Нарушена{check.bad_seq ? ` на записи № ${check.bad_seq}` : ''}: {check.reason}.
					{/if}
				</p>
			{/if}
		</section>
	{/if}
{/if}

<style>
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid var(--line);
		margin-bottom: 24px;
	}
	h1 {
		margin: 0;
		font-size: 28px;
		font-weight: normal;
		letter-spacing: 0.08em;
	}
	section {
		margin-top: 40px;
	}
	.bad {
		color: var(--seal);
	}
</style>
