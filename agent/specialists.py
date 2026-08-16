from __future__ import annotations

import logging
from typing import Any

from .client import ModelClient
from .environment import WarehouseEnvironment
from .messages import AgentMessage

logger = logging.getLogger(__name__)


class DispatcherAgent:
    name = "dispatcher"

    def __init__(self, model: ModelClient) -> None:
        self.model = model
        self.task_states: dict[str, str] = {}
        self.task_details: dict[str, str] = {}
        self.events: list[str] = []

    def create_request(self, task: dict[str, Any]) -> AgentMessage:
        task_id = str(task["task_id"])
        if self.task_states.get(task_id) == "waiting":
            raise ValueError(f"task {task_id} is already waiting")

        instruction = self.model.complete(
            system_prompt=(
                "You are a warehouse dispatch agent. Write one short, direct "
                "instruction for a picking robot. Use only the task facts supplied."
            ),
            user_prompt=(
                f"Task {task_id}: pick {task['quantity']} units of "
                f"{task['sku']} from {task['location']}."
            ),
        )
        self.task_states[task_id] = "waiting"
        self.task_details.pop(task_id, None)
        self.events.append(f"request created for {task_id}")
        return AgentMessage(
            sender=self.name,
            receiver="robot-1",
            performative="request",
            conversation_id=task_id,
            payload={"task_id": task_id, "instruction": instruction},
        )

    def handle(self, message: AgentMessage) -> None:
        if message.receiver != self.name:
            raise ValueError("message delivered to the wrong agent")
        if message.sender != "robot-1":
            raise ValueError("dispatcher expected a reply from robot-1")
        if message.performative not in {"inform", "refuse"}:
            raise ValueError("dispatcher expected a robot reply")
        if message.conversation_id not in self.task_states:
            raise ValueError("reply does not match a known task")
        if self.task_states[message.conversation_id] != "waiting":
            raise ValueError("task is not waiting for a reply")

        payload_task_id = str(message.payload.get("task_id", ""))
        if payload_task_id != message.conversation_id:
            raise ValueError("reply task_id does not match its conversation")

        state = "completed" if message.performative == "inform" else "refused"
        detail = str(message.payload.get("detail", "")).strip()
        self.task_states[message.conversation_id] = state
        self.task_details[message.conversation_id] = detail
        event = f"task {message.conversation_id} {state}"
        self.events.append(event)
        logger.info(event)


class RobotAgent:
    name = "robot-1"

    def __init__(self, environment: WarehouseEnvironment) -> None:
        self.environment = environment
        self.events: list[str] = []

    def handle(self, message: AgentMessage) -> AgentMessage:
        if message.receiver != self.name:
            raise ValueError("message delivered to the wrong agent")
        if message.sender != "dispatcher":
            raise ValueError("robot expected a request from the dispatcher")
        if message.performative != "request":
            raise ValueError("robot expected a request")

        task_id = str(message.payload.get("task_id", ""))
        if not task_id or task_id != message.conversation_id:
            raise ValueError("request task_id does not match its conversation")

        task = self.environment.tasks.get(task_id)
        if task is None:
            performative = "refuse"
            detail = "task is not present in the warehouse view"
        elif self.environment.stock_at(task["location"], task["sku"]) < task["quantity"]:
            performative = "refuse"
            detail = "not enough stock at the requested location"
        else:
            try:
                self.environment.pick(
                    task["location"],
                    task["sku"],
                    task["quantity"],
                )
            except (TypeError, ValueError) as exc:
                performative = "refuse"
                detail = f"pick could not be completed: {exc}"
            else:
                performative = "inform"
                detail = "pick completed"

        self.events.append(f"{task_id}: {detail}")
        return AgentMessage(
            sender=self.name,
            receiver="dispatcher",
            performative=performative,
            conversation_id=message.conversation_id,
            payload={"task_id": task_id, "detail": detail},
        )
