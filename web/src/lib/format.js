const TZ = 'Europe/Moscow';

export function fmtDate(iso) {
	return iso ? new Date(iso).toLocaleDateString('ru-RU', { timeZone: TZ, day: 'numeric', month: 'long', year: 'numeric' }) : '';
}

export function fmtDateTime(iso) {
	return iso
		? new Date(iso).toLocaleString('ru-RU', { timeZone: TZ, day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
		: '';
}

export const DAYS = [
	['MO', 'пн'],
	['TU', 'вт'],
	['WE', 'ср'],
	['TH', 'чт'],
	['FR', 'пт'],
	['SA', 'сб'],
	['SU', 'вс']
];

export function scheduleText(s) {
	if (!s) return '';
	const parts = Object.fromEntries(s.rrule.split(';').map((p) => p.split('=')));
	let what = { DAILY: 'Ежедневно', WEEKLY: 'Еженедельно', MONTHLY: 'Ежемесячно' }[parts.FREQ] ?? s.rrule;
	if (parts.BYDAY) what += ': ' + parts.BYDAY.split(',').map((d) => DAYS.find(([k]) => k === d)?.[1] ?? d).join(', ');
	if (parts.BYMONTHDAY) what += `, ${parts.BYMONTHDAY}-го числа`;
	return `${what} в ${s.time}`;
}

export const STATUS = {
	draft: 'Черновик',
	pending: 'На подписи',
	returned: 'Возвращён',
	partial: 'Подписан 1 из 2',
	enacted: 'Вступил в силу',
	withdrawn: 'Отозван',
	request: 'Заявка',
	rejected: 'Отклонена'
};

export const KIND = { new: 'Новый закон', amend: 'Правка', repeal: 'Упразднение' };
