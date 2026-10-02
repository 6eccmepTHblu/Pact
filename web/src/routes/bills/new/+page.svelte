<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.js';
	import { KIND } from '#lib/format.js';
	import { toForm, toPayload } from '#lib/billForm.js';
	import BillForm from '#lib/BillForm.svelte';

	const kind = page.url.searchParams.get('kind') ?? 'new';
	const lawId = Number(page.url.searchParams.get('law')) || null;

	let tree = $state([]);
	let law = $state(null);
	let form = $state(toForm());
	let error = $state('');
	let busy = $state(false);

	onMount(async () => {
		tree = await api('/pakt');
		if (lawId) {
			law = await api('/laws/' + lawId);
			// Правка начинается с действующей редакции.
			if (kind === 'amend') form = toForm('', { ...law.versions[0], placement: null });
		}
	});

	async function create(e) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			const bill = await api('/bills', { method: 'POST', body: { kind, target_law_id: lawId, ...toPayload(form, kind) } });
			goto('/bills/' + bill.id, { replaceState: true });
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

<form onsubmit={create}>
	<BillForm bind:form {kind} {tree} />
	{#if error}<p class="error">{error}</p>{/if}
	<div class="actions">
		<button disabled={busy}>Создать черновик</button>
		<button type="button" class="quiet" onclick={() => history.back()}>Отмена</button>
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
