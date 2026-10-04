<script>
	import { base } from '$app/paths';
	import Prompts from '$lib/components/workspace/Prompts.svelte';
</script>

<Prompts showCreateOnMount={true} createModalCloseHref={`${base}/workspace/prompts`} />
