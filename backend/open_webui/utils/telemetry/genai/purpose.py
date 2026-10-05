TASK_PURPOSES = {
    'title_generation': 'title_generation',
    'follow_up_generation': 'followup_generation',
    'tags_generation': 'tags_generation',
    'query_generation': 'retrieval_query',
}


def purpose_for_task(task) -> str:
    return TASK_PURPOSES.get(str(task), 'primary')
