<script>
	import { onMount } from 'svelte';
	import { api } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';

	const KEY_URL = {
		openai: 'https://platform.openai.com/api-keys',
		gemini: 'https://aistudio.google.com/apikey'
	};

	let s = $state(null); // сохранённые настройки
	let form = $state({ provider: 'openai', api_key: '', chat_model: '', embed_model: '' });
	let models = $state({ chat: [], embed: [] });
	let modelsMsg = $state('');
	let result = $state(null);
	let message = $state('');
	let error = $state('');
	let busy = $state(false);

	let hasKey = $derived(!!form.api_key.trim() || !!s?.keys[form.provider]);
	// Текущая модель видна в списке, даже если провайдер её не вернул.
	const withCurrent = (list, current) => (current && !list.includes(current) ? [current, ...list] : list);
	let chatOptions = $derived(withCurrent(models.chat, form.chat_model));
	let embedOptions = $derived(withCurrent(models.embed, form.embed_model));

	onMount(async () => {
		s = await api('/settings/llm');
		form = { provider: s.provider, api_key: '', chat_model: s.chat_model, embed_model: s.embed_model };
		loadModels();
	});

	const probe = () => ({ provider: form.provider, api_key: form.api_key.trim() || null });

	async function loadModels() {
		models = { chat: [], embed: [] };
		modelsMsg = '';
		if (!hasKey) return (modelsMsg = 'Введите API-ключ, чтобы загрузить список моделей.');
		modelsMsg = 'Загружаю модели…';
		try {
			models = await api('/settings/llm/models', { method: 'POST', body: probe() });
			modelsMsg = '';
		} catch (e) {
			modelsMsg = 'Не удалось получить модели: ' + e.message;
		}
	}

	function changeProvider() {
		const p = s.providers.find((x) => x.id === form.provider);
		const same = form.provider === s.provider;
		form.chat_model = same ? s.chat_model : p.chat;
		form.embed_model = same ? s.embed_model : p.embed;
		form.api_key = '';
		result = null;
		loadModels();
	}

	async function act(fn) {
		busy = true;
		error = message = '';
		try {
			await fn();
		} catch (e) {
			error = e.message;
		} finally {
			busy = false;
		}
	}

	const test = () =>
		act(async () => {
			result = null;
			result = await api('/settings/llm/test', { method: 'POST', body: { ...probe(), chat_model: form.chat_model, embed_model: form.embed_model } });
		});

	const save = () =>
		act(async () => {
			s = await api('/settings/llm', { method: 'PUT', body: { ...probe(), chat_model: form.chat_model, embed_model: form.embed_model } });
			form.api_key = '';
			message = s.reindex
				? 'Сохранено. Модель эмбеддингов сменилась: поиск похожих законов пересчитается при следующей разметке.'
				: 'Сохранено.';
		});
</script>

<h1>Настройки</h1>

{#if session.me.role !== 'husband'}
	<p class="muted">Настройки доступны супругу.</p>
{:else if s}
	<section>
		<h2>Языковая модель</h2>

		<label>
			Провайдер
			<select bind:value={form.provider} onchange={changeProvider}>
				{#each s.providers as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
			</select>
		</label>

		<label>
			API-ключ
			<input
				type="password"
				autocomplete="off"
				bind:value={form.api_key}
				onchange={loadModels}
				placeholder={s.keys[form.provider] ? `сохранён (${s.keys[form.provider]}), оставьте пустым` : 'не задан'}
			/>
			<a class="hint" href={KEY_URL[form.provider]} target="_blank" rel="noopener">Где взять ключ</a>
		</label>

		<label>
			Модель для текста
			<select bind:value={form.chat_model} disabled={!chatOptions.length}>
				{#each chatOptions as m (m)}<option value={m}>{m}</option>{/each}
			</select>
		</label>

		<label>
			Модель эмбеддингов (поиск похожих законов)
			<select bind:value={form.embed_model} disabled={!embedOptions.length}>
				{#each embedOptions as m (m)}<option value={m}>{m}</option>{/each}
			</select>
		</label>

		{#if modelsMsg}<p class="muted small">{modelsMsg}</p>{/if}

		<div class="actions">
			<button class="quiet" onclick={test} disabled={busy || !hasKey}>Проверить соединение</button>
			<button onclick={save} disabled={busy || !form.chat_model || !form.embed_model}>Сохранить</button>
		</div>

		{#if busy && !result}<p class="muted small">Проверяю…</p>{/if}
		{#if result}
			<ul class="result">
				{#each [['Текст', result.chat], ['Эмбеддинги', result.embed]] as [name, r]}
					<li class:bad={!r.ok}>
						<strong>{r.ok ? '✓' : '✗'} {name}</strong>
						{#if r.ok}
							{r.model} · {r.ms} мс{#if r.dims} · {r.dims} измерений{/if}
						{:else}
							{r.error}
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
		{#if message}<p class="ok" role="status">{message}</p>{/if}
		{#if error}<p class="error" role="alert">{error}</p>{/if}
	</section>
{/if}

<style>
	h1 {
		margin: 0 0 16px;
		font-size: 28px;
	}
	h2 {
		margin: 0 0 12px;
		font-size: 20px;
	}
	section {
		display: grid;
		gap: 16px;
	}
	.hint {
		font-size: 14px;
		justify-self: start;
	}
	.small {
		font-size: 15px;
		margin: 0;
	}
	.result {
		margin: 0;
		padding: 12px 16px;
		list-style: none;
		border: 1px solid var(--line);
		background: var(--field);
		display: grid;
		gap: 6px;
		font-size: 15px;
		overflow-wrap: anywhere;
	}
	.result li {
		color: var(--ok);
	}
	.result li.bad {
		color: var(--seal);
	}
	.ok {
		color: var(--ok);
	}
</style>
