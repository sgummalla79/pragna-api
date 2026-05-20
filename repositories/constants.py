"""
Domain constants for the repository and service layers.

All string literals that represent domain values (statuses, types, roles) live
here. Importing from this module instead of inlining raw strings prevents typos,
enables IDE navigation, and makes value changes a single-file edit.
"""


class SnapshotType:
    """Valid values for skill_snapshots.type."""
    DRAFT     = "draft"
    PUBLISHED = "published"
    EXECUTION = "execution"


class ExecutionStatus:
    """Valid values for skill_executions.status."""
    RUNNING       = "running"
    COMPLETE      = "complete"
    HALTED        = "halted"
    ERROR         = "error"
    INVALID_INPUT = "invalid_input"


class MessageRole:
    """Valid values for conversation_messages.role."""
    USER      = "user"
    ASSISTANT = "assistant"


class MessageType:
    """Valid values for conversation_messages.message_type."""
    CHAT         = "chat"
    ARTIFACT_REF = "artifact_ref"
    ERROR        = "error"


class MessageState:
    """Valid values for conversation_messages.message_state."""
    VISIBLE = "visible"
    HIDDEN  = "hidden"


class ArtifactStatus:
    """Valid values for conversation_artifacts.status."""
    PENDING_REVIEW    = "pending_review"
    REVIEW_FAILED     = "review_failed"
    REVIEW_PASSED     = "review_passed"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVED          = "approved"


class ArtifactType:
    """Valid values for conversation_artifacts.artifact_type."""
    DOCUMENT = "document"


class ConfigKey:
    """Well-known keys used in the user_config table."""
    THEME         = "theme"
    BEDROCK_URL   = "bedrock_url"
    BEDROCK_TOKEN = "bedrock_token"
    BEDROCK_MODE  = "bedrock_mode"
