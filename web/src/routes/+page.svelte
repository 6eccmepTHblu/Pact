<script>
	import { onMount } from 'svelte';
	import { api } from '#lib/api.js';
	import { fmtDate } from '#lib/format.js';
	import { session } from '#lib/session.svelte.js';
	import AskPakt from '#lib/AskPakt.svelte';

	let tree = $state(null);
	let check = $state(null);
	let copied = $state(false);

	onMount(async () => {
		tree = await api('/pakt');
	});

	async function verify() {
		try {
			check = await api('/journal/verify');
		} catch (err) {
			check = { ok: false, reason: err.message };
		}
	}
</script>

<h1>Пакт</h1>

{#if tree?.length}<AskPakt />{/if}

<a class="new" href="/bills/new">{session.me.role === 'husband' ? 'Новый законопроект' : 'Подать заявку'}</a>

{#if tree && !tree.length}
	<p class="muted">В Пакте пока нет законов.</p>
{/if}

{#each tree ?? [] as s (s.id)}
	<section>
		<h2><span class="num">{s.number}.</span> {s.title}</h2>
		{#each s.articles as a (a.id)}
			<h3><span class="num">{s.number}.{a.number}</span> {a.title}</h3>
			<ul>
				{#each a.laws as l (l.id)}
					<li class:repealed={l.status === 'repealed'}>
						<a href="/laws/{l.id}">
							<span class="num">{s.number}.{a.number}.{l.number}</span>
							<span class="title">{l.title}</span>
						</a>
						{#if l.status === 'repealed'}
							<small class="muted">Утратил силу {fmtDate(l.repealed_at)}</small>
						{/if}
					</li>
				{/each}
			</ul>
		{/each}
	</section>
{/each}

{#if session.me.calendar}
	<p class="calendar muted">
		Календарь с расписаниями законов:
		<a href={'webcal://' + location.host + session.me.calendar}>подписаться</a> ·
		<button class="link" onclick={() => navigator.clipboard.writeText(location.origin + session.me.calendar).then(() => (copied = true))}>
			{copied ? 'ссылка скопирована' : 'скопировать ссылку'}
		</button>
	</p>
{/if}

{#if session.me.role === 'husband'}
	<footer>
		<button class="link" onclick={verify}>Проверить журнал</button>
		{#if check}
			<span class:error={!check.ok}>
				{#if check.ok}Цепочка цела: {check.count} записей.{:else}Нарушена{check.bad_seq ? ` на записи № ${check.bad_seq}` : ''}: {check.reason}.{/if}
			</span>
		{/if}
	</footer>
{/if}

<style>
	h1 {
		margin: 0 0 16px;
		font-size: 32px;
		letter-spacing: 0.08em;
	}
	.new {
		display: inline-block;
		margin-bottom: 24px;
		padding: 10px 18px;
		border: 1px solid var(--ink);
		background: var(--ink);
		color: var(--paper);
		text-decoration: none;
	}
	section {
		margin-bottom: 32px;
	}
	h2 {
		margin: 0 0 8px;
		font-size: 22px;
		border-bottom: 1px solid var(--line);
	}
	h3 {
		margin: 16px 0 4px;
		font-size: 18px;
		font-style: italic;
	}
	ul {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li {
		padding: 6px 0;
	}
	li a {
		display: flex;
		gap: 10px;
		text-decoration: none;
	}
	li .num {
		flex: none;
		min-width: 3.2em;
	}
	.repealed .title {
		color: var(--muted);
		text-decoration: line-through;
	}
	li small {
		display: block;
		padding-left: calc(3.2em + 10px);
	}
	.calendar {
		margin-top: 48px;
		font-size: 15px;
	}
	footer {
		margin-top: 16px;
		font-size: 15px;
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}
</style>
