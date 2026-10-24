from queue import TaskQueue
from worker import TaskWorker


def submit_and_process(name: str) -> str:
    """Submit one task and process the queue."""
    queue = TaskQueue()
    queue.add(name)
    return TaskWorker(queue).run_once()
