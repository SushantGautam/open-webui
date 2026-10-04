<script>
	import { base } from '$app/paths';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { config } from '$lib/stores';

	onMount(() => {
		if (!($config?.features.enable_admin_analytics ?? true)) {
			goto(`${base}/admin`, { replaceState: true });
		} else {
			goto(`${base}/?settings=admin%3Aanalytics`, { replaceState: true });
		}
	});
</script>
