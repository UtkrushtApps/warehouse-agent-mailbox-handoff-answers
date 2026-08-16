from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import fcntl

from .messages import AgentMessage


def load_fixture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixture must be a JSON object")
    if not isinstance(data.get("tasks"), list) or not data["tasks"]:
        raise ValueError("fixture must contain tasks")
    if not isinstance(data.get("inventory"), list):
        raise ValueError("fixture must contain inventory")
    return data


class FileInbox:
    """A small process-safe mailbox backed by a local JSON file.

    Every read-modify-write operation is protected by a lock and committed with
    an atomic replace. Receiving messages removes only messages matching the
    requested receiver and optional conversation, leaving all unrelated work in
    its original order.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(f"{self.path.name}.lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> list[AgentMessage]:
        if not self.path.exists():
            return []

        text = self.path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise ValueError("inbox file must contain a JSON array")
        return [AgentMessage.model_validate(item) for item in raw]

    def _write_unlocked(self, messages: list[AgentMessage]) -> None:
        serialized = [message.model_dump(mode="json") for message in messages]
        content = json.dumps(serialized, indent=2)

        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    def _read(self) -> list[AgentMessage]:
        with self._locked():
            return self._read_unlocked()

    def _write(self, messages: list[AgentMessage]) -> None:
        with self._locked():
            self._write_unlocked(messages)

    def send(self, message: AgentMessage) -> None:
        validated = AgentMessage.model_validate(message)
        with self._locked():
            messages = self._read_unlocked()
            messages.append(validated)
            self._write_unlocked(messages)

    def receive_for(
        self,
        receiver: str,
        conversation_id: str | None = None,
    ) -> list[AgentMessage]:
        """Remove and return only messages addressed to the given recipient.

        When a conversation ID is supplied, messages for other conversations
        addressed to the same agent are also retained.
        """
        with self._locked():
            messages = self._read_unlocked()
            selected: list[AgentMessage] = []
            retained: list[AgentMessage] = []
            for message in messages:
                receiver_matches = message.receiver == receiver
                conversation_matches = (
                    conversation_id is None
                    or message.conversation_id == conversation_id
                )
                if receiver_matches and conversation_matches:
                    selected.append(message)
                else:
                    retained.append(message)
            if selected:
                self._write_unlocked(retained)
            return selected

    def remove_conversation(self, conversation_id: str) -> int:
        """Remove residual messages for one finished or failed conversation."""
        with self._locked():
            messages = self._read_unlocked()
            retained = [
                message
                for message in messages
                if message.conversation_id != conversation_id
            ]
            removed = len(messages) - len(retained)
            if removed:
                self._write_unlocked(retained)
            return removed

    def count(self, conversation_id: str | None = None) -> int:
        messages = self._read()
        if conversation_id is None:
            return len(messages)
        return sum(
            message.conversation_id == conversation_id for message in messages
        )


class WarehouseEnvironment:
    def __init__(
        self,
        tasks: dict[str, dict[str, Any]],
        inventory: dict[tuple[str, str], int],
    ) -> None:
        self.tasks = tasks
        self.inventory = inventory

    @classmethod
    def from_fixture(cls, fixture: dict[str, Any]) -> "WarehouseEnvironment":
        tasks: dict[str, dict[str, Any]] = {}
        for source in fixture["tasks"]:
            task = dict(source)
            task_id = str(task["task_id"])
            quantity = int(task["quantity"])
            if quantity <= 0:
                raise ValueError("task quantity must be positive")
            task["task_id"] = task_id
            task["location"] = str(task["location"])
            task["sku"] = str(task["sku"])
            task["quantity"] = quantity
            tasks[task_id] = task

        inventory: dict[tuple[str, str], int] = {}
        for source in fixture["inventory"]:
            location = str(source["location"])
            sku = str(source["sku"])
            quantity = int(source["quantity"])
            if quantity < 0:
                raise ValueError("inventory quantity cannot be negative")
            inventory[(location, sku)] = quantity

        return cls(tasks=tasks, inventory=inventory)

    def stock_at(self, location: str, sku: str) -> int:
        return self.inventory.get((location, sku), 0)

    def pick(self, location: str, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("requested quantity must be positive")
        available = self.stock_at(location, sku)
        if quantity > available:
            raise ValueError("requested quantity exceeds available stock")
        self.inventory[(location, sku)] = available - quantity
