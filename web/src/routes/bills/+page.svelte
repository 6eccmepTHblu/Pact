<script>
	import { onMount } from 'svelte';
	import { api } from '#lib/api.js';
	import { KIND, fmtDate, statusFor } from '#lib/format.js';
	import { session } from '#lib/session.svelte.js';

	let bills = $state(null);

	onMount(async () => {
		bills = await api('/bills');
	});

	// Что требует действия текущей стороны — наверх.
	const mine = (b) =>
		session.me.role === 'wife'
			? ['pending', 'partial'].includes(b.status)
			: ['request', 'draft', 'returned'].includes(b.status);
	const done = (b) => ['enacted', 'withdrawn', 'rejected'].includes(b.status);

	let groups = $derived(
		bills && [
			['Ждут вас', bills.filter(mine)],
			['На рассмотрении у другой стороны', bills.filter((b) => !mine(b) && !done(b))],
			['Завершённые', bills.filter(done)]
		]
	);
</script>

<h1>Законопроекты</h1>

<a class="new" href="/bills/new">{session.me.role === 'husband' ? 'Новый законопроект' : 'Подать заявку'}</a>

{#if bills && !bills.length}
	<p class="muted">Законопроектов пока нет.</p>
{/if}

{#each groups ?? [] as [name, list]}
	{#if list.length}
		<h2>{name}</h2>
		<ul>
			{#each list as b (b.id)}
				<li>
					<a href="/bills/{b.id}">
						<span class="title">
							{#if b.number}<span class="num">{b.number}</span>{/if}
							{b.title}
						</span>
						<small class="muted">{KIND[b.kind]} · <span class="st {b.status}">{statusFor(session.me.role, b.status)}</span> · {fmtDate(b.updated_at)}</small>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
{/each}

<style>
	h1 {
		margin: 0 0 16px;
		font-size: 28px;
	}
	h2 {
		margin: 28px 0 4px;
		font-size: 17px;
		color: var(--muted);
		letter-spacing: 0.04em;
	}
	.new {
		display: inline-block;
		padding: 10px 18px;
		background: var(--ink);
		color: var(--paper);
		text-decoration: none;
	}
	ul {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li a {
		display: grid;
		gap: 2px;
		padding: 10px 0;
		border-bottom: 1px solid var(--line);
		text-decoration: none;
	}
	.title .num {
		margin-right: 6px;
	}
	small {
		font-size: 14px;
	}
	.st.returned,
	.st.request,
	.st.pending,
	.st.partial {
		color: var(--seal);
	}
</style>
