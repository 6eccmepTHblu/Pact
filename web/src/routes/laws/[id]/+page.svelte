<script>
	import { page } from '$app/state';
	import { api } from '#lib/api.js';
	import { fmtDate, fmtDateTime, scheduleText } from '#lib/format.js';
	import { api as call } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';
	import SignatureView from '#lib/SignatureView.svelte';

	let law = $state(null);
	let error = $state('');

	$effect(() => {
		law = null;
		api('/laws/' + page.params.id)
			.then((l) => (law = l))
			.catch((e) => (error = e.message));
	});

	let marking = $state(false);

	async function markDone() {
		marking = true;
		try {
			await call(`/laws/${law.id}/done`, { method: 'POST' });
			law = await call('/laws/' + law.id);
		} catch (e) {
			error = e.message;
		} finally {
			marking = false;
		}
	}

	let current = $derived(law?.versions[0]);
	let history = $derived(law?.versions.slice(1) ?? []);
</script>

{#if error}<p class="error">{error}</p>{/if}

{#if law}
	<p class="crumbs muted">
		<span class="num">{law.section.number}.</span> {law.section.title} ·
		<span class="num">{law.section.number}.{law.article.number}</span> {law.article.title}
	</p>
	<h1><span class="num">{law.number}</span> {current.title}</h1>

	{#if law.status === 'repealed'}
		<div class="repealed">
			<strong>Утратил силу {fmtDate(law.repealed_at)}</strong>
			<p>{law.repeal.reason}</p>
			<div class="sigs">
				{#each law.repeal.signatures as sig}<SignatureView {sig} />{/each}
			</div>
		</div>
	{/if}

	<p class="text">{current.official_text}</p>

	{#if current.schedule || current.tags.length}
		<p class="meta muted">
			{#if current.schedule}<span>{scheduleText(current.schedule)}</span>{/if}
			{#each current.tags as t}<span class="tag">{t}</span>{/each}
		</p>
	{/if}

	{#each [['Опирается на', law.refs], ['На него опираются', law.referenced_by]] as [name, list]}
		{#if list.length}
			<div class="links">
				<span class="muted">{name}</span>
				{#each list as l (l.id)}
					<a href="/laws/{l.id}" class:gone={l.status === 'repealed'}><span class="num">{l.number}</span> {l.title}</a>
				{/each}
			</div>
		{/if}
	{/each}

	<details>
		<summary>Исходный текст</summary>
		<blockquote>{current.original_text}</blockquote>
	</details>

	<div class="sigs">
		{#each current.signatures as sig}<SignatureView {sig} />{/each}
	</div>
	<p class="muted small">
		{#if current.version_no === 1}
			Вступил в силу {fmtDate(law.enacted_at)}
		{:else}
			Редакция {current.version_no} от {fmtDate(current.signed_at)}, в силе с {fmtDate(law.enacted_at)}
		{/if}
	</p>

	{#if law.done.length}
		<p class="muted small">Исполнено: {law.done.slice(0, 5).map(fmtDateTime).join(', ')}{law.done.length > 5 ? '…' : ''}</p>
	{/if}

	{#if law.status === 'active'}
		<div class="actions">
			{#if session.me.role === 'husband'}
				{#if current.schedule}
					<button onclick={markDone} disabled={marking}>Отметить исполнение</button>
				{/if}
				<a class="btn quiet" href="/bills/new?kind=amend&law={law.id}">Подготовить правку</a>
				<a class="btn quiet" href="/bills/new?kind=repeal&law={law.id}">Упразднить</a>
			{:else}
				<a class="btn quiet" href="/bills/new?kind=amend&law={law.id}">Попросить правку</a>
				<a class="btn quiet" href="/bills/new?kind=repeal&law={law.id}">Попросить упразднить</a>
			{/if}
		</div>
	{/if}

	{#if history.length}
		<h2>Прежние редакции</h2>
		{#each history as v (v.version_no)}
			<details>
				<summary>Редакция {v.version_no} от {fmtDate(v.signed_at)}</summary>
				<p><strong>{v.title}</strong></p>
				<p>{v.official_text}</p>
				<blockquote>{v.original_text}</blockquote>
				<div class="sigs">
					{#each v.signatures as sig}<SignatureView {sig} />{/each}
				</div>
			</details>
		{/each}
	{/if}
{/if}

<style>
	.crumbs {
		margin: 0 0 4px;
		font-size: 15px;
	}
	h1 {
		margin: 0 0 16px;
		font-size: 26px;
		line-height: 1.25;
	}
	h2 {
		margin: 40px 0 8px;
		font-size: 20px;
	}
	.text {
		font-size: 19px;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 14px;
		font-size: 15px;
	}
	.links {
		display: grid;
		gap: 4px;
		margin: 12px 0;
		font-size: 16px;
	}
	.links a {
		text-decoration: none;
	}
	.links .gone {
		text-decoration: line-through;
		color: var(--muted);
	}
	.tag::before {
		content: '#';
	}
	details {
		margin: 16px 0;
		border-top: 1px solid var(--line);
		padding-top: 8px;
	}
	summary {
		cursor: pointer;
		color: var(--muted);
		min-height: 32px;
	}
	blockquote {
		margin: 8px 0;
		padding-left: 12px;
		border-left: 3px solid var(--line);
		font-style: italic;
	}
	.sigs {
		display: flex;
		flex-wrap: wrap;
		gap: 16px 24px;
		margin-top: 24px;
	}
	.small {
		font-size: 14px;
	}
	.repealed {
		margin-bottom: 20px;
		padding: 12px 16px;
		border: 1px solid var(--seal);
		color: var(--seal);
	}
	.repealed p {
		color: var(--ink);
		margin: 4px 0 0;
	}
	.btn {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 18px;
		border: 1px solid var(--ink);
		background: var(--ink);
		color: var(--paper);
		text-decoration: none;
	}
	.btn.quiet {
		background: transparent;
		color: var(--ink);
		border-color: var(--line);
	}
</style>
