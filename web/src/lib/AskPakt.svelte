<script>
	import { api } from '#lib/api.js';

	let question = $state('');
	let result = $state(null);
	let error = $state('');
	let busy = $state(false);

	// Ответ — текст с номерами [4.1.1]; номера становятся ссылками без {@html}.
	let parts = $derived.by(() => {
		if (!result) return [];
		const ids = Object.fromEntries(result.laws.map((l) => [l.number, l.id]));
		return result.answer.split(/(\[\d+\.\d+\.\d+\])/).map((t) => {
			const n = t.match(/^\[(\d+\.\d+\.\d+)\]$/)?.[1];
			return n && ids[n] ? { n, id: ids[n] } : { t };
		});
	});

	async function submit(e) {
		e.preventDefault();
		busy = true;
		error = '';
		result = null;
		try {
			result = await api('/ask', { method: 'POST', body: { question } });
		} catch (err) {
			error = err.message;
		} finally {
			busy = false;
		}
	}
</script>

<form class="ask" onsubmit={submit}>
	<input bind:value={question} placeholder="Спросить Пакт: что там про цветы?" aria-label="Вопрос к Пакту" minlength="2" required />
	<button disabled={busy}>{busy ? '…' : 'Спросить'}</button>
</form>

{#if error}<p class="error">{error}</p>{/if}
{#if result}
	<div class="answer" role="status">
		<p>
			{#each parts as p}{#if p.id}<a href="/laws/{p.id}" class="num">[{p.n}]</a>{:else}{p.t}{/if}{/each}
		</p>
		{#if result.laws.length}
			<ul>
				{#each result.laws as l (l.id)}
					<li><a href="/laws/{l.id}"><span class="num">{l.number}</span> {l.title}</a></li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}

<style>
	.ask {
		display: flex;
		gap: 8px;
		margin-bottom: 12px;
	}
	.ask input {
		flex: 1;
		min-width: 0;
	}
	.answer {
		margin-bottom: 24px;
		padding: 12px 16px;
		border-left: 3px solid var(--seal);
		background: var(--field);
	}
	.answer p {
		margin: 0;
	}
	.answer a.num {
		text-decoration: none;
	}
	ul {
		margin: 8px 0 0;
		padding: 0;
		list-style: none;
		font-size: 15px;
	}
	li a {
		text-decoration: none;
	}
</style>
