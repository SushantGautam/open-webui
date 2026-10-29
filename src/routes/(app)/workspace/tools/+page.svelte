<script>
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { config } from '$lib/stores';

	import Tools from '$lib/components/workspace/Tools.svelte';

	// config starts as undefined and is filled in once the backend config loads. Decide
	// only after that: an onMount check runs on cold load, sees undefined, and sends a
	// user with tools enabled to /workspace -> Models (intermittent).
	$: if ($config !== undefined && !$config?.features?.enable_tools) {
		goto(`${base}/workspace`, { replaceState: true });
	}
</script>

{#if $config?.features?.enable_tools}
	<Tools />
{/if}
