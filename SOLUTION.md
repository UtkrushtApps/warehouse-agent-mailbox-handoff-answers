# Solution Steps

1. Fix the file inbox so `receive_for` partitions messages into selected and retained lists, writing back only the retained messages instead of clearing the entire mailbox.

2. Protect each inbox read-modify-write transaction with a file lock and commit JSON updates through an atomic temporary-file replacement to avoid lost updates between agents or processes.

3. Allow mailbox reads to be scoped by both receiver and conversation ID so a coordinator handling one task does not consume another task waiting for the same agent.

4. Keep the existing request/inform/refuse contract and validate sender, receiver, performative, conversation ID, and payload task ID at each specialist boundary.

5. Have the dispatcher create a model-generated robot instruction and place the task in the `waiting` state before sending the request.

6. Have the robot use the warehouse environment as the authoritative task and inventory view, returning `inform` after a successful pick or `refuse` with a clear reason when execution is unsafe.

7. Replace the one-pass dispatcher-then-robot loop with a bounded routing loop. Route matching mailbox messages to their addressed agent, enqueue robot replies, and continue until the dispatcher reaches a terminal state.

8. Record events at the moment each action occurs rather than concatenating per-agent logs afterward, preserving request, robot execution, and dispatcher completion ordering.

9. Convert robot processing exceptions into contract-compliant refusal replies, and mark unroutable or invalid dispatcher exchanges as explicit failed terminal states.

10. At termination, remove only residual messages for the completed conversation, retain unrelated mailbox work, and report total pending messages, conversation-specific pending messages, failure detail, and a safe-terminal indicator.

11. Validate warehouse quantities and prevent non-positive picks so inventory cannot be increased or moved into an invalid state.

12. Run `python -m agent --selfcheck` and `python -m pytest -q invariants`; with model credentials configured, run `python -m agent` to execute and print the final workflow report.

