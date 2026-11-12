"""Normalized message type and the provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr

from ..config import Account


@dataclass
class EmailMessage:
    account_id: str
    message_id: str
    thread_id: str
    sender: str  # "Name <addr>" or bare address
    subject: str
    date: datetime  # timezone-aware
    text: str = ""
    html: str = ""
    headers: dict[str, str] = field(default_factory=dict)  # lower-cased names

    @property
    def address(self) -> str:
        return parseaddr(self.sender)[1].lower()


class EmailProvider(ABC):
    def __init__(self, account: Account):
        self.account = account

    @abstractmethod
    def fetch_unread(self, since: datetime, limit: int) -> list[EmailMessage]:
        """Return unread inbox messages received after *since* (newest first, at most *limit*)."""
