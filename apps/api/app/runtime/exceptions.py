class ApprovalRequired(Exception):
    """Raised by the approval block to pause the run."""
    def __init__(self, block_id: str, message: str = ""):
        self.block_id = block_id
        self.message = message
        super().__init__(message)


class ClarificationRequired(Exception):
    """Raised by a Brain block when the task context is too ambiguous to proceed."""
    def __init__(self, block_id: str, question: str):
        self.block_id = block_id
        self.question = question
        super().__init__(question)
