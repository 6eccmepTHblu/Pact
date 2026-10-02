<script>
	import { fmtDateTime } from '#lib/format.js';

	let { sig } = $props();
</script>

<!-- svg строит сервер только из координат штрихов, поэтому {@html} здесь безопасен -->
<figure>
	<div class="ink">{@html sig.svg}</div>
	<figcaption>{sig.name}, {fmtDateTime(sig.signed_at)}</figcaption>
</figure>

<style>
	figure {
		margin: 0;
		max-width: 260px;
	}
	.ink {
		border-bottom: 1px solid var(--line);
	}
	.ink :global(svg) {
		display: block;
		width: 100%;
		height: auto;
		max-height: 90px;
	}
	figcaption {
		color: var(--muted);
		font-size: 14px;
	}
</style>
