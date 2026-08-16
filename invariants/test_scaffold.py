from pathlib import Path

from agent.coordinator import WarehouseCoordinator
from agent.environment import FileInbox, WarehouseEnvironment, load_fixture
from agent.messages import AgentMessage
from agent.specialists import DispatcherAgent, RobotAgent

BASE_DIR = Path("/root/task")


def test_fixture_loads() -> None:
    fixture = load_fixture(BASE_DIR / "fixtures" / "sample.json")
    assert fixture
    assert len(fixture["tasks"]) >= 1
    assert WarehouseEnvironment.from_fixture(fixture) is not None


def test_message_schema_round_trip() -> None:
    message = AgentMessage(
        sender="health-a",
        receiver="health-b",
        performative="request",
        conversation_id="health-check",
        payload={"task_id": "health-task"},
    )
    restored = AgentMessage.model_validate(message.model_dump())
    assert restored == message


def test_public_components_are_available(tmp_path: Path) -> None:
    inbox = FileInbox(tmp_path / "probe.json")
    assert inbox.count() == 0
    assert all(
        callable(component)
        for component in (WarehouseCoordinator, DispatcherAgent, RobotAgent)
    )
