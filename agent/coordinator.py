from __future__ import annotations

from typing import Any

from .environment import FileInbox
from .messages import AgentMessage
from .specialists import DispatcherAgent, RobotAgent


class WarehouseCoordinator:
    """Routes mailbox messages until the requested conversation is terminal."""

    _TERMINAL_STATES = {"completed", "refused", "failed"}

    def __init__(
        self,
        dispatcher: DispatcherAgent,
        robot: RobotAgent,
        inbox: FileInbox,
    ) -> None:
        self.dispatcher = dispatcher
        self.robot = robot
        self.inbox = inbox

    def _failure_reply(self, request: AgentMessage, exc: Exception) -> AgentMessage:
        task_id = request.conversation_id
        detail = f"robot failed to process request: {type(exc).__name__}: {exc}"
        self.robot.events.append(f"{task_id}: {detail}")
        return AgentMessage(
            sender=self.robot.name,
            receiver=self.dispatcher.name,
            performative="refuse",
            conversation_id=task_id,
            payload={"task_id": task_id, "detail": detail},
        )

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task["task_id"])
        ordered_events: list[str] = []
        orchestration_failure: str | None = None

        request = self.dispatcher.create_request(task)
        ordered_events.append(self.dispatcher.events[-1])
        self.inbox.send(request)

        # A local exchange normally needs two routing passes: one for the
        # request and one for the reply. The bounded loop also makes a missing
        # reply an explicit terminal failure rather than leaving a waiting task.
        for _ in range(10):
            progressed = False
            for agent in (self.dispatcher, self.robot):
                messages = self.inbox.receive_for(
                    agent.name,
                    conversation_id=task_id,
                )
                for message in messages:
                    progressed = True
                    if agent is self.robot:
                        try:
                            reply = self.robot.handle(message)
                        except Exception as exc:
                            reply = self._failure_reply(message, exc)
                        ordered_events.append(self.robot.events[-1])
                        self.inbox.send(reply)
                    else:
                        try:
                            self.dispatcher.handle(message)
                        except Exception as exc:
                            orchestration_failure = (
                                "dispatcher failed to process reply: "
                                f"{type(exc).__name__}: {exc}"
                            )
                            self.dispatcher.task_states[task_id] = "failed"
                            self.dispatcher.task_details[task_id] = orchestration_failure
                            self.dispatcher.events.append(
                                f"task {task_id} failed: {orchestration_failure}"
                            )
                        ordered_events.append(self.dispatcher.events[-1])

            state = self.dispatcher.task_states.get(task_id, "failed")
            if state in self._TERMINAL_STATES:
                break
            if not progressed:
                orchestration_failure = "no routable message remained for the waiting task"
                self.dispatcher.task_states[task_id] = "failed"
                self.dispatcher.task_details[task_id] = orchestration_failure
                event = f"task {task_id} failed: {orchestration_failure}"
                self.dispatcher.events.append(event)
                ordered_events.append(event)
                break
        else:
            orchestration_failure = "message routing exceeded the safety limit"
            self.dispatcher.task_states[task_id] = "failed"
            self.dispatcher.task_details[task_id] = orchestration_failure
            event = f"task {task_id} failed: {orchestration_failure}"
            self.dispatcher.events.append(event)
            ordered_events.append(event)

        # Remove only residual messages belonging to this conversation. Work
        # for other tasks and recipients remains in the shared inbox.
        discarded = self.inbox.remove_conversation(task_id)
        conversation_pending = self.inbox.count(task_id)
        status = self.dispatcher.task_states[task_id]
        detail = self.dispatcher.task_details.get(task_id, "")

        return {
            "task_id": task_id,
            "status": status,
            "detail": detail,
            "failure": orchestration_failure,
            "pending_messages": self.inbox.count(),
            "conversation_pending_messages": conversation_pending,
            "discarded_conversation_messages": discarded,
            "safe_terminal": (
                status in self._TERMINAL_STATES and conversation_pending == 0
            ),
            "events": ordered_events,
        }
