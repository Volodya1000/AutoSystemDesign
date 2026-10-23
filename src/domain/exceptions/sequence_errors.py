"""Domain exceptions raised by sequence-model validators."""

from domain.exceptions.architecture_errors import ArchitectureValidationError


class SequenceIntegrityError(ArchitectureValidationError):
    """The sequence AST breaks referential integrity across its context."""

    error_code: str = "SEQUENCE_INTEGRITY_ERROR"


class SequenceTopologyError(ArchitectureValidationError):
    """A component message contradicts C4 or has no matching request."""

    error_code: str = "SEQUENCE_TOPOLOGY_ERROR"

    def __init__(self, source: str, target: str, explanation: str) -> None:
        super().__init__(
            message=f"Message {source} -> {target}: {explanation}",
            affected_node_identifiers=[source, target],
        )


class SharedClientLifelineError(ArchitectureValidationError):
    """A client boundary component is used by more than one business role."""

    error_code: str = "SHARED_CLIENT_LIFELINE"

    def __init__(self, client_lifeline_id: str, business_role_ids: list[str]) -> None:
        message: str = (
            f"Client component lifeline '{client_lifeline_id}' is shared by "
            f"multiple business roles: {business_role_ids}. Each boundary "
            f"client must belong to exactly one actor."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[client_lifeline_id],
        )
        self.client_lifeline_id: str = client_lifeline_id
        self.business_role_ids: list[str] = business_role_ids


class AsyncDeliveryModeError(ArchitectureValidationError):
    """A fire-and-forget message is not marked as asynchronous."""

    error_code: str = "ASYNC_DELIVERY_MODE_REQUIRED"

    def __init__(self, action_name: str, message_kind: str) -> None:
        message: str = (
            f"Message '{action_name}' has message_kind '{message_kind}' "
            f"but delivery_mode is not 'async'. Fire-and-forget messages "
            f"must set delivery_mode='async'."
        )
        super().__init__(message=message)
        self.action_name: str = action_name
        self.message_kind: str = message_kind
