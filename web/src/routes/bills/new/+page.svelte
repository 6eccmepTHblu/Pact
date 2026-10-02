<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.js';
	import { KIND } from '#lib/format.js';

	const kind = page.url.searchParams.get('kind') ?? 'new';
	const lawId = Number(page.url.searchParams.get('law')) || null;

	let law = $state(null);
	let text = $state('');
	let error = $state('');
	let busy = $state(false);

	onMount(async () => {
		if (lawId) law = await api('/laws/' + lawId);
	});

	async function create(analyze) {
		busy = true;
		error = '';
		try {
			const bill = await api('/bills', {
				method: 'POST',
				body: { kind, target_law_id: lawId, original_text: text }
			});
			goto(`/bills/${bill.id}${analyze ? '?analyze=1' : ''}`, { replaceState: true });
		} catch (err) {
			error = err.message;
			busy = false;
		}
	}
</script>

<h1>{KIND[kind]}</h1>
{#if law}
	<p class="muted"><span class="num">{law.number}</span> {law.versions[0].title}</p>
{/if}

<form onsubmit={(e) => (e.preventDefault(), create(kind !== 'repeal'))}>
	<label>
		{kind === 'repeal' ? 'Причина упразднения' : kind === 'amend' ? 'Что изменить' : 'Пожелание, как есть'}
		<textarea bind:value={text} required rows="5"></textarea>
	</label>
	{#if error}<p class="error">{error}</p>{/if}
	<div class="actions">
		{#if kind === 'repeal'}
			<button disabled={busy}>Создать черновик</button>
		{:else}
			<button disabled={busy}>Разметить</button>
			<button type="button" class="quiet" disabled={busy || !text.trim()} onclick={() => create(false)}>Заполнить вручную</button>
		{/if}
	</div>
</form>

<style>
	h1 {
		margin: 0 0 8px;
		font-size: 26px;
	}
	form {
		margin-top: 16px;
	}
</style>
