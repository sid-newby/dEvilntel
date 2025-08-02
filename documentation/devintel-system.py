@dataclass
class DevEvent:
    id: str
    type: EventType
    timestamp: datetime
    session_id: str
    content: Dict[str, Any]
    stack_trace: Optional[str]
    context: Dict[str, Any]
    embedding: Optional[List[float]] = None  # Use List[float] for serialization

    def to_changelog_entry(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "content": self.content,
            "context": self.context,
            "hash": hashlib.sha256(
                json.dumps(self.content, sort_keys=True).encode()
            ).hexdigest()
        }
