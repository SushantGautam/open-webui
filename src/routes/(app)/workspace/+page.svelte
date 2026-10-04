<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { config, user } from '$lib/stores';
	import { onMount } from 'svelte';

	onMount(() => {
		if ($user?.role !== 'admin') {
			if ($user?.permissions?.workspace?.models) {
				goto(`${base}/workspace/models`, { replaceState: true });
			} else if ($user?.permissions?.workspace?.knowledge) {
				goto(`${base}/workspace/knowledge`, { replaceState: true });
			} else if ($user?.permissions?.workspace?.prompts) {
				goto(`${base}/workspace/prompts`, { replaceState: true });
			} else if ($config?.features?.enable_plugins && $user?.permissions?.workspace?.tools) {
				goto(`${base}/workspace/tools`, { replaceState: true });
			} else if ($user?.permissions?.workspace?.skills) {
				goto(`${base}/workspace/skills`, { replaceState: true });
			} else {
				goto(`${base}/`, { replaceState: true });
			}
		} else {
			goto(`${base}/workspace/models`, { replaceState: true });
		}
	});
</script>
