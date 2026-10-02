<script>
	import { DAYS } from '#lib/format.js';

	// form — объект из toForm(), правится на месте; tree — дерево Пакта для подсказок места.
	let { form = $bindable(), kind, tree = [] } = $props();

	let articles = $derived(
		tree.find((s) => s.title.toLowerCase() === form.section.trim().toLowerCase())?.articles ?? []
	);
</script>

<div class="form">
	<label>
		{kind === 'repeal' ? 'Причина упразднения' : 'Исходный текст пожелания'}
		<textarea bind:value={form.original_text} required></textarea>
	</label>

	{#if kind !== 'repeal'}
		<label>
			Название закона
			<input bind:value={form.title} placeholder="Следить за свежестью цветов в Вечной вазе" />
		</label>
		<label>
			Официальный текст
			<textarea bind:value={form.official_text} placeholder="Супруг ежедневно проверяет…"></textarea>
		</label>

		{#if kind === 'new'}
			<div class="row">
				<label>
					Раздел
					<input bind:value={form.section} list="sections" placeholder="Цветы" />
				</label>
				<label>
					Статья
					<input bind:value={form.article} list="articles" placeholder="Вечная ваза" />
				</label>
			</div>
			<datalist id="sections">
				{#each tree as s}<option value={s.title}></option>{/each}
			</datalist>
			<datalist id="articles">
				{#each articles as a}<option value={a.title}></option>{/each}
			</datalist>
		{/if}

		<label>
			Теги через запятую
			<input bind:value={form.tags} placeholder="Цветы, Ежедневно" />
		</label>

		<div class="row">
			<label>
				Расписание
				<select bind:value={form.freq}>
					<option value="">Без расписания</option>
					<option value="DAILY">Ежедневно</option>
					<option value="WEEKLY">Еженедельно</option>
					<option value="MONTHLY">Ежемесячно</option>
				</select>
			</label>
			{#if form.freq}
				<label>
					Время
					<input type="time" bind:value={form.time} />
				</label>
			{/if}
		</div>
		{#if form.freq === 'WEEKLY'}
			<div class="days">
				{#each DAYS as [code, name]}
					<label class="day">
						<input type="checkbox" value={code} bind:group={form.days} />
						{name}
					</label>
				{/each}
			</div>
		{:else if form.freq === 'MONTHLY'}
			<label>
				Число месяца
				<input type="number" min="1" max="31" bind:value={form.monthday} />
			</label>
		{/if}
	{/if}
</div>

<style>
	.form {
		display: grid;
		gap: 16px;
	}
	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
	}
	.days {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.day {
		display: flex;
		align-items: center;
		gap: 6px;
		min-height: 44px;
		padding: 0 10px;
		border: 1px solid var(--line);
		color: var(--ink);
	}
	.day input {
		width: auto;
		min-height: 0;
	}
</style>
