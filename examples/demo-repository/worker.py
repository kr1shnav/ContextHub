from queue import TaskQueue


class TaskWorker:
    def __init__(self, queue: TaskQueue) -> None:
        self.queue = queue

    def run_once(self) -> str:
        return f"processed: {self.queue.pop()}"
