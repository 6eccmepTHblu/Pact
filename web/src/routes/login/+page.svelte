<script>
	import { goto } from '$app/navigation';
	import { api } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';

	let login = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	async function submit(e) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			session.me = await api('/auth/login', { method: 'POST', body: { login, password } });
			goto('/', { replaceState: true });
		} catch (err) {
			error = err.message;
		} finally {
			busy = false;
		}
	}
</script>

<h1>Пакт</h1>
<p class="sub">Свод законов семьи</p>

<form onsubmit={submit}>
	<label>
		Логин
		<input bind:value={login} autocomplete="username" autocapitalize="none" required />
	</label>
	<label>
		Пароль
		<input bind:value={password} type="password" autocomplete="current-password" required />
	</label>
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	<button disabled={busy}>Войти</button>
</form>

<style>
	h1 {
		margin: 15vh 0 0;
		font-size: 44px;
		font-weight: normal;
		letter-spacing: 0.08em;
		text-align: center;
	}
	.sub {
		margin: 0 0 40px;
		color: var(--muted);
		text-align: center;
		font-style: italic;
	}
	form {
		display: grid;
		gap: 16px;
	}
	label {
		display: grid;
		gap: 4px;
		color: var(--muted);
		font-size: 15px;
	}
	input {
		min-height: 44px;
		padding: 0 12px;
		border: 1px solid var(--line);
		border-radius: 2px;
		background: var(--field);
		font-size: 17px;
	}
	input:focus {
		outline: 2px solid var(--ink);
		outline-offset: -1px;
	}
	.error {
		margin: 0;
		color: var(--seal);
	}
</style>
