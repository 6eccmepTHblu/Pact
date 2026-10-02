<script>
	import { onMount } from 'svelte';

	// onsign({ width, height, strokes }) — strokes: [[[x, y], ...], ...] в CSS-пикселях холста.
	let { onsign, oncancel, busy = false } = $props();

	const MIN_POINTS = 20; // «несколько штрихов»: столько точек не оставить случайным касанием

	let canvas;
	let ctx;
	let strokes = []; // обычный массив: точек много, реактивность не нужна
	let current = null;
	let points = $state(0);

	function size() {
		const r = canvas.getBoundingClientRect();
		const dpr = window.devicePixelRatio || 1;
		canvas.width = r.width * dpr;
		canvas.height = r.height * dpr;
		ctx = canvas.getContext('2d');
		ctx.scale(dpr, dpr);
		ctx.lineWidth = 2.5;
		ctx.lineCap = ctx.lineJoin = 'round';
		ctx.strokeStyle = '#111';
		strokes.forEach(drawStroke);
	}

	onMount(() => {
		size();
		window.addEventListener('resize', size);
		return () => window.removeEventListener('resize', size);
	});

	function point(e) {
		const r = canvas.getBoundingClientRect();
		const clamp = (v, max) => Math.round(Math.min(Math.max(v, 0), max) * 10) / 10;
		return [clamp(e.clientX - r.left, r.width), clamp(e.clientY - r.top, r.height)];
	}

	const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

	// Тот же способ сглаживания, что и в SVG на сервере: кривые через середины отрезков.
	function drawStroke(pts) {
		ctx.beginPath();
		ctx.moveTo(...pts[0]);
		if (pts.length === 1) ctx.lineTo(pts[0][0] + 0.1, pts[0][1]);
		for (let i = 1; i < pts.length - 1; i++) ctx.quadraticCurveTo(...pts[i], ...mid(pts[i], pts[i + 1]));
		if (pts.length > 1) ctx.lineTo(...pts[pts.length - 1]);
		ctx.stroke();
	}

	function down(e) {
		canvas.setPointerCapture(e.pointerId);
		current = [point(e)];
		strokes.push(current);
		points++;
		drawStroke(current);
	}

	function move(e) {
		if (!current) return;
		const coalesced = e.getCoalescedEvents?.() ?? [];
		for (const ev of coalesced.length ? coalesced : [e]) {
			const p = point(ev);
			const last = current[current.length - 1];
			if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 1.5) continue;
			const prev = current[current.length - 2] ?? last;
			current.push(p);
			points++;
			ctx.beginPath();
			ctx.moveTo(...mid(prev, last));
			ctx.quadraticCurveTo(...last, ...mid(last, p));
			ctx.stroke();
		}
	}

	function up() {
		current = null;
	}

	function clear() {
		strokes = [];
		points = 0;
		ctx.clearRect(0, 0, canvas.width, canvas.height);
	}

	function submit() {
		const r = canvas.getBoundingClientRect();
		onsign({ width: Math.round(r.width), height: Math.round(r.height), strokes });
	}
</script>

<div class="pad" role="dialog" aria-label="Подпись">
	<div class="area">
		<canvas
			bind:this={canvas}
			onpointerdown={down}
			onpointermove={move}
			onpointerup={up}
			onpointercancel={up}
		></canvas>
		<div class="line">Подпись</div>
	</div>
	<div class="buttons">
		<button class="plain" onclick={oncancel}>Отмена</button>
		<button class="plain" onclick={clear} disabled={!points}>Очистить</button>
		<button class="go" onclick={submit} disabled={points < MIN_POINTS || busy}>Подписать</button>
	</div>
</div>

<style>
	/* Белый лист при любой теме: подпись выглядит как на бумаге. */
	.pad {
		position: fixed;
		inset: 0;
		z-index: 10;
		display: flex;
		flex-direction: column;
		background: #fff;
		color: #111;
		padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
	}
	.area {
		position: relative;
		flex: 1;
	}
	canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		touch-action: none;
		cursor: crosshair;
	}
	.line {
		position: absolute;
		left: 24px;
		right: 24px;
		bottom: 30%;
		border-top: 1px solid #999;
		padding-top: 4px;
		color: #888;
		font-size: 14px;
		pointer-events: none;
	}
	.buttons {
		display: flex;
		gap: 12px;
		padding: 12px 16px 16px;
		border-top: 1px solid #ddd;
	}
	.buttons button {
		flex: 1;
		min-height: 48px;
		border-radius: 2px;
		font-size: 17px;
	}
	.plain {
		background: #fff;
		color: #111;
		border: 1px solid #ccc;
	}
	.go {
		background: #111;
		color: #fff;
		border: 1px solid #111;
	}
</style>
