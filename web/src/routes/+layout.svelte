<script>
	let { children } = $props();
</script>

<main>
	{@render children()}
</main>

<style>
	:global(:root) {
		--paper: #f6f1e7;
		--ink: #1f1c17;
		--muted: #6f675a;
		--line: #d9cfbd;
		--seal: #8a1c1c;
		--field: #fffdf8;
		color-scheme: light;
	}
	@media (prefers-color-scheme: dark) {
		:global(:root) {
			--paper: #1a1814;
			--ink: #ece5d6;
			--muted: #a59c8b;
			--line: #3a352c;
			--seal: #d9675f;
			--field: #24211b;
			color-scheme: dark;
		}
	}
	:global(*) {
		box-sizing: border-box;
	}
	:global(body) {
		margin: 0;
		background: var(--paper);
		color: var(--ink);
		font: 17px/1.5 Georgia, 'Times New Roman', serif;
		-webkit-tap-highlight-color: transparent;
	}
	:global(button, input) {
		font: inherit;
		color: inherit;
	}
	:global(button) {
		min-height: 44px;
		padding: 0 18px;
		border: 1px solid var(--ink);
		border-radius: 2px;
		background: var(--ink);
		color: var(--paper);
		cursor: pointer;
	}
	:global(button.quiet) {
		background: transparent;
		color: var(--ink);
		border-color: var(--line);
	}
	:global(button:disabled) {
		opacity: 0.5;
	}
	main {
		max-width: 560px;
		margin: 0 auto;
		padding: max(24px, env(safe-area-inset-top)) 16px 32px;
	}
</style>
