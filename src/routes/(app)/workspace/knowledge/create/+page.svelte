<script>
	import { base } from '$app/paths';
	import Knowledge from '$lib/components/workspace/Knowledge.svelte';
</script>

<Knowledge showCreateOnMount={true} createModalCloseHref={`${base}/workspace/knowledge`} />
