"""
User information value object.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class UserInfo:
    """
    Value object representing user information.
    """
    email: str
    name: str
    
    def __post_init__(self):
        if not self.email:
            raise ValueError("Email cannot be empty")
        if "@" not in self.email:
            raise ValueError("Invalid email format")
        if not self.name:
            raise ValueError("Name cannot be empty")
    
    def is_same_user(self, other_email: str) -> bool:
        """Check if this user has the same email as provided."""
        return self.email.lower() == other_email.lower()