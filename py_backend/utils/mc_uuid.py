import hashlib
import uuid

def get_minecraft_uuid(username: str) -> str:
    """
    Generates a deterministic Minecraft offline-mode UUID (v3) for a username.
    Matches Java's UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(StandardCharsets.UTF_8))
    """
    name = f"OfflinePlayer:{username}"
    # Minecraft uses MD5 (UUID v3) but with a specific approach
    hash_bytes = hashlib.md5(name.encode('utf-8')).digest()

    # Convert to list of bytes to modify
    hash_list = list(hash_bytes)

    # Set version to 3 (MD5)
    hash_list[6] = (hash_list[6] & 0x0f) | 0x30
    # Set variant to IETF
    hash_list[8] = (hash_list[8] & 0x3f) | 0x80

    return str(uuid.UUID(bytes=bytes(hash_list)))
