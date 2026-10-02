import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit({ adapter: adapter({ fallback: 'index.html' }) })],
	// В dev API крутится в docker compose на 8200.
	server: { proxy: { '/api': 'http://127.0.0.1:8200' } }
});
