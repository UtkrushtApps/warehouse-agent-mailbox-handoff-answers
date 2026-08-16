from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .client import ModelClient
from .coordinator import WarehouseCoordinator
from .environment import FileInbox, WarehouseEnvironment, load_fixture
from .messages import AgentMessage
from .specialists import DispatcherAgent, RobotAgent

BASE_DIR = Path("/root/task")
FIXTURE_PATH = BASE_DIR / "fixtures" / "sample.json"


def selfcheck() -> None:
    load_dotenv(BASE_DIR / ".env")
    fixture = load_fixture(FIXTURE_PATH)
    AgentMessage(
        sender="check-a",
        receiver="check-b",
        performative="request",
        conversation_id="check-conversation",
        payload={"task_id": fixture["tasks"][0]["task_id"]},
    )
    if os.getenv("OPENAI_API_KEY"):
        ModelClient().complete(
            system_prompt="You are a readiness checker.",
            user_prompt="Reply with the word ready.",
        )
    print("scaffold ready")


def run() -> None:
    load_dotenv(BASE_DIR / ".env")
    fixture = load_fixture(FIXTURE_PATH)
    environment = WarehouseEnvironment.from_fixture(fixture)
    inbox_path = BASE_DIR / "inbox.json"
    inbox_path.unlink(missing_ok=True)

    client = ModelClient()
    dispatcher = DispatcherAgent(client)
    robot = RobotAgent(environment)
    coordinator = WarehouseCoordinator(
        dispatcher=dispatcher,
        robot=robot,
        inbox=FileInbox(inbox_path),
    )
    report = coordinator.run(fixture["tasks"][0])
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Warehouse agent workflow")
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
    else:
        run()


if __name__ == "__main__":
    main()
