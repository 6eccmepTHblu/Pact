// Форма законопроекта <-> тело запроса API.

export function toForm(originalText = '', p = null) {
	const parts = Object.fromEntries((p?.schedule?.rrule ?? '').split(';').filter(Boolean).map((x) => x.split('=')));
	return {
		original_text: originalText,
		title: p?.title ?? '',
		official_text: p?.official_text ?? '',
		tags: (p?.tags ?? []).join(', '),
		freq: parts.FREQ ?? '',
		days: parts.BYDAY ? parts.BYDAY.split(',') : [],
		monthday: parts.BYMONTHDAY ?? '',
		time: p?.schedule?.time ?? '09:00',
		section: p?.placement?.section ?? '',
		article: p?.placement?.article ?? ''
	};
}

export function toPayload(f, kind) {
	if (kind === 'repeal') return { original_text: f.original_text };
	let schedule = null;
	if (f.freq) {
		let rrule = 'FREQ=' + f.freq;
		if (f.freq === 'WEEKLY' && f.days.length) rrule += ';BYDAY=' + f.days.join(',');
		if (f.freq === 'MONTHLY' && f.monthday) rrule += ';BYMONTHDAY=' + f.monthday;
		schedule = { rrule, time: f.time || '09:00' };
	}
	// Черновик можно сохранить и недозаполненным: тогда формулировки ещё нет.
	const prepared =
		f.title.trim() && f.official_text.trim()
			? {
					title: f.title,
					official_text: f.official_text,
					tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean),
					schedule,
					placement: kind === 'new' && f.section.trim() && f.article.trim() ? { section: f.section, article: f.article } : null
				}
			: null;
	return { original_text: f.original_text, prepared };
}
