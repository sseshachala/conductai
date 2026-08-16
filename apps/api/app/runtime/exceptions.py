class ApprovalRequired(Exception):
    """Raised by an approval block or a Guard rule with action=approval to pause the run."""
    def __init__(self, block_id: str, message: str = "", metadata: dict | None = None):
        self.block_id = block_id
        self.message = message
        # Optional extras merged into the approval_requested run_event payload —
        # e.g. approval_id, rule_id, and decide URL when a Guard rule triggered the pause.
        self.metadata = metadata or {}
        super().__init__(message)


class ClarificationRequired(Exception):
    """Raised by a Brain block when the task context is too ambiguous to proceed."""
    def __init__(self, block_id: str, question: str):
        self.block_id = block_id
        self.question = question
        super().__init__(question)
