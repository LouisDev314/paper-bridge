import uuid

def generate_id(prefix: str = "") -> str:
    """Generate a unique ID, optionally with a prefix."""
    random_uuid = str(uuid.uuid4()).replace("-", "")
    if prefix:
        return f"{prefix}_{random_uuid}"
    return random_uuid
