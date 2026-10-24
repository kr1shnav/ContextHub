class TaskQueue:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, name: str) -> None:
        self.items.append(name)

    def pop(self) -> str:
        return self.items.pop(0)
