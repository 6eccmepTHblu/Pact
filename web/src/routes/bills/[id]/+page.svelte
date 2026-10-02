<script>
	import { goto, replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.js';
	import { KIND, scheduleText, statusFor } from '#lib/format.js';
	import { toForm, toPayload } from '#lib/billForm.js';
	import { session } from '#lib/session.svelte.js';
	import BillForm from '#lib/BillForm.svelte';
	import SignaturePad from '#lib/SignaturePad.svelte';
	import SignatureView from '#lib/SignatureView.svelte';

	let bill = $state(null);
	let form = $state(null);
	let tree = $state([]);
	let error = $state('');
	let busy = $state(false);
	let signing = $state(false);
	let returning = $state(false);
	let comment = $state('');
	let analyzing = $state(false);
	let rejecting = $state(false);
	let hintOpen = $state(false);
	let hint = $state('');
	let reason = $state('');

	const url = (action = '') => `/bills/${page.params.id}${action}`;
	let husband = $derived(session.me.role === 'husband');
	let editable = $derived(husband && ['draft', 'returned'].includes(bill?.status));
	let canSign = $derived(
		bill &&
			(husband
				? bill.kind === 'repeal' && editable
				: bill.status === (bill.kind === 'repeal' ? 'partial' : 'pending'))
	);
	let canReturn = $derived(bill && !husband && ['pending', 'partial'].includes(bill.status));
	let p = $derived(bill?.prepared);

	function show(b) {
		bill = b;
		form = toForm(b.original_text, b.prepared);
	}

	$effect(() => {
		api(url())
			.then((b) => {
				show(b);
				// Пришли со страницы создания с «Разметить»: запускаем конвейер сразу.
				if (page.url.searchParams.has('analyze')) {
					replaceState(url(), {});
					analyze();
				}
			})
			.catch((e) => (error = e.message));
		if (husband) api('/pakt').then((t) => (tree = t));
	});

	async function act(fn) {
		busy = true;
		error = '';
		try {
			await fn();
		} catch (err) {
			error = err.message;
		} finally {
			busy = false;
		}
	}

	// rework=true — повторная разметка: сначала сохраняем ручные правки, чтобы LLM видела актуальный вариант.
	const analyze = (hint = '', rework = false) =>
		act(async () => {
			analyzing = true;
			try {
				if (rework) await save();
				show(await api(url('/analyze'), { method: 'POST', body: { hint: hint.trim() || null } }));
			} finally {
				analyzing = false;
			}
		});

	const reanalyze = () => (bill.prepared ? (hintOpen = true) : analyze());

	function sendHint(e) {
		e.preventDefault();
		hintOpen = false;
		analyze(hint, true);
		hint = '';
	}

	const save = async () => show(await api(url('/prepared'), { method: 'PUT', body: toPayload(form, bill.kind) }));

	const submit = () =>
		act(async () => {
			await save();
			show(await api(url('/submit'), { method: 'POST' }));
		});

	const startSign = () =>
		act(async () => {
			if (editable) await save();
			signing = true;
		});

	const sign = (data) =>
		act(async () => {
			show(await api(url('/sign'), { method: 'POST', body: { ...data, text_hash: bill.text_hash } }));
			signing = false;
		});

	const sendBack = (e) => {
		e.preventDefault();
		act(async () => {
			show(await api(url('/return'), { method: 'POST', body: { comment } }));
			returning = false;
		});
	};

	// Взять заявку в работу и сразу разметить (упразднение не размечается).
	const accept = () =>
		act(async () => {
			show(await api(url('/accept'), { method: 'POST' }));
			if (bill.kind !== 'repeal') analyze();
		});

	const sendReject = (e) => {
		e.preventDefault();
		act(async () => {
			show(await api(url('/reject'), { method: 'POST', body: { comment: reason } }));
			rejecting = false;
		});
	};

	const remove = () =>
		confirm('Удалить отозванный законопроект? Это нельзя отменить.') &&
		act(async () => {
			await api(url(), { method: 'DELETE' });
			goto('/bills', { replaceState: true });
		});

	const withdraw = () =>
		confirm('Отозвать законопроект? Он останется в истории, но в работу больше не вернётся.') &&
		act(async () => show(await api(url('/withdraw'), { method: 'POST' })));
</script>

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if bill}
	<p class="muted kicker">
		{KIND[bill.kind]} · <span class="st">{statusFor(session.me.role, bill.status)}</span>
		{#if bill.number}
			· {bill.kind === 'new' && bill.status !== 'enacted' ? 'предварительно ' : ''}<span class="num">{bill.number}</span>
		{/if}
	</p>
	<h1>{bill.title}</h1>

	{#if bill.status === 'rejected' && bill.reject_reason}
		<aside class="comment">
			<strong>Причина отказа</strong>
			<p>{bill.reject_reason}</p>
		</aside>
	{/if}

	{#if bill.status === 'request'}
		<h2>{husband ? 'Заявка супруги' : 'Ваша заявка'}</h2>
		<p class="text">{bill.original_text}</p>
		{#if husband}
			{#if rejecting}
				<form class="return" onsubmit={sendReject}>
					<label>
						Почему отклоняется
						<textarea bind:value={reason} required></textarea>
					</label>
					<div class="actions">
						<button disabled={busy}>Отклонить</button>
						<button type="button" class="quiet" onclick={() => (rejecting = false)}>Отмена</button>
					</div>
				</form>
			{:else}
				<div class="actions">
					<button onclick={accept} disabled={busy}>Взять в работу</button>
					<button class="quiet" onclick={() => (rejecting = true)}>Отклонить</button>
				</div>
			{/if}
		{/if}
	{:else if bill.status === 'returned' && bill.wife_comment && husband}
		<aside class="comment">
			<strong>Комментарий супруги</strong>
			<p>{bill.wife_comment}</p>
		</aside>
	{/if}

	{#if bill.target && bill.kind !== 'new'}
		<p class="muted">
			{bill.kind === 'repeal' ? 'Упраздняется' : 'Изменяется'}
			<a href="/laws/{bill.target.id}"><span class="num">{bill.target.number}</span> {bill.target.title}</a>
		</p>
	{/if}

	{#if bill.kind === 'repeal' && bill.target?.referenced_by.length && bill.status !== 'enacted'}
		<aside class="warnings">
			На этот закон опираются действующие законы — проверьте, не нужно ли их изменить или упразднить:
			<ul>
				{#each bill.target.referenced_by as l (l.id)}
					<li><a href="/laws/{l.id}"><span class="num">{l.number}</span> {l.title}</a></li>
				{/each}
			</ul>
		</aside>
	{/if}

	{#if bill.status === 'request' || bill.status === 'rejected'}
		<!-- заявка показана выше -->
	{:else if !husband && !bill.prepared && bill.kind !== 'repeal'}
		<p class="muted">Супруг готовит законопроект по вашей заявке:</p>
		<blockquote>{bill.original_text}</blockquote>
	{:else if editable}
		{#if analyzing}
			<p class="analyzing" role="status">Размечаю: разбор, место в Пакте, официальная редакция, проверка смысла. Обычно 10–20 секунд.</p>
		{/if}
		{#if bill.warnings.length}
			<ul class="warnings">
				{#each bill.warnings as w}<li>{w}</li>{/each}
			</ul>
		{/if}
		<BillForm bind:form kind={bill.kind} {tree} targetId={bill.target?.id} />
		<div class="actions">
			{#if bill.kind === 'repeal'}
				<button onclick={startSign} disabled={busy}>Подписать упразднение</button>
			{:else}
				<button onclick={submit} disabled={busy}>Отправить на подпись</button>
			{/if}
			<button class="quiet" onclick={() => act(save)} disabled={busy}>Сохранить</button>
			{#if bill.kind !== 'repeal'}
				<button class="quiet" onclick={reanalyze} disabled={busy || hintOpen}>{bill.prepared ? 'Разметить заново' : 'Разметить'}</button>
			{/if}
			<button class="link" onclick={withdraw} disabled={busy}>Отозвать</button>
		</div>
		{#if hintOpen}
			<form class="hint" onsubmit={sendHint}>
				<label>
					Что уточнить или поправить
					<textarea bind:value={hint} rows="3" placeholder="Например: только по выходным; короче; в раздел «Дом»"></textarea>
				</label>
				<p class="muted small">LLM увидит текущую разметку и ваше указание. Можно оставить пустым — тогда разметка с нуля.</p>
				<div class="actions">
					<button disabled={busy}>Разметить заново</button>
					<button type="button" class="quiet" onclick={() => (hintOpen = false)}>Отмена</button>
				</div>
			</form>
		{/if}
	{:else}
		{#if bill.kind === 'repeal'}
			<h2>Причина</h2>
			<p>{bill.original_text}</p>
		{:else if p}
			{#if bill.kind === 'amend'}
				<h2>Действующая редакция</h2>
				<p class="old">{bill.target.official_text}</p>
				<h2>Новая редакция</h2>
			{/if}
			<p class="text">{p.official_text}</p>
			<p class="meta muted">
				{#if p.placement}<span>Раздел «{p.placement.section}», статья «{p.placement.article}»</span>{/if}
				{#if p.schedule}<span>{scheduleText(p.schedule)}</span>{/if}
				{#each p.tags as t}<span>#{t}</span>{/each}
			</p>
			{#if bill.refs.length}
				<p class="muted">
					Опирается на:
					{#each bill.refs as l, i (l.id)}{i ? ', ' : ''}<a href="/laws/{l.id}"><span class="num">{l.number}</span> {l.title}</a>{/each}
				</p>
			{/if}
			<details>
				<summary>Исходный текст</summary>
				<blockquote>{bill.original_text}</blockquote>
			</details>
		{/if}

		{#if bill.signatures.length}
			<div class="sigs">
				{#each bill.signatures as sig}<SignatureView {sig} />{/each}
			</div>
		{/if}

		{#if bill.status === 'withdrawn' && husband}
			<div class="actions">
				<button class="quiet" onclick={remove} disabled={busy}>Удалить законопроект</button>
			</div>
		{/if}

		{#if bill.status === 'enacted' && bill.law_id}
			<p><a href="/laws/{bill.law_id}">Открыть закон в Пакте</a></p>
		{/if}

		{#if canSign || canReturn}
			{#if returning}
				<form class="return" onsubmit={sendBack}>
					<label>
						Что поправить
						<textarea bind:value={comment} required></textarea>
					</label>
					<div class="actions">
						<button disabled={busy}>Вернуть</button>
						<button type="button" class="quiet" onclick={() => (returning = false)}>Отмена</button>
					</div>
				</form>
			{:else}
				<div class="actions">
					<button onclick={startSign} disabled={busy}>Подписать</button>
					<button class="quiet" onclick={() => (returning = true)}>Вернуть с правками</button>
				</div>
			{/if}
		{/if}
	{/if}

	{#if signing}
		<SignaturePad onsign={sign} oncancel={() => (signing = false)} {busy} />
		{#if error}<p class="error floating" role="alert">{error}</p>{/if}
	{/if}
{/if}

<style>
	.kicker {
		margin: 0;
		font-size: 15px;
	}
	.st {
		color: var(--seal);
	}
	h1 {
		margin: 4px 0 16px;
		font-size: 26px;
		line-height: 1.25;
	}
	h2 {
		margin: 20px 0 4px;
		font-size: 15px;
		color: var(--muted);
		letter-spacing: 0.04em;
	}
	.text {
		font-size: 19px;
	}
	.old {
		color: var(--muted);
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 14px;
		font-size: 15px;
	}
	.comment {
		margin: 0 0 20px;
		padding: 12px 16px;
		border-left: 3px solid var(--seal);
		background: var(--field);
	}
	.comment p {
		margin: 4px 0 0;
	}
	details {
		margin: 16px 0;
	}
	summary {
		cursor: pointer;
		color: var(--muted);
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
	.return {
		margin-top: 24px;
	}
	.hint {
		margin-top: 20px;
		padding: 12px 16px;
		border: 1px solid var(--line);
		background: var(--field);
	}
	.hint .actions {
		margin-top: 12px;
	}
	.small {
		font-size: 14px;
		margin: 8px 0 0;
	}
	.analyzing {
		padding: 12px 16px;
		border: 1px dashed var(--line);
		color: var(--muted);
		font-style: italic;
	}
	.warnings :global(a) {
		color: var(--ink);
	}
	aside.warnings ul {
		margin: 8px 0 0;
		padding-left: 20px;
	}
	.warnings {
		margin: 0 0 20px;
		padding: 12px 16px 12px 32px;
		border-left: 3px solid var(--seal);
		background: var(--field);
		color: var(--seal);
	}
	.floating {
		position: fixed;
		z-index: 11;
		top: 16px;
		left: 16px;
		right: 16px;
		padding: 8px 12px;
		background: #fff;
		border: 1px solid currentColor;
	}
</style>
