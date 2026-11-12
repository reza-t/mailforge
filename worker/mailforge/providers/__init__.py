from .base import EmailMessage, EmailProvider
from .gmail import GmailProvider
from .outlook import OutlookProvider
from .yahoo import YahooProvider

# To add a provider: implement EmailProvider, register it here, extend Account.provider.
PROVIDERS: dict[str, type[EmailProvider]] = {
    "gmail": GmailProvider,
    "outlook": OutlookProvider,
    "yahoo": YahooProvider,
}

__all__ = ["PROVIDERS", "EmailMessage", "EmailProvider"]
