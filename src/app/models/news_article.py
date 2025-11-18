from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NewsArticle:
    """
    Represents a news article scraped from a news source.
    """
    title: str
    description: Optional[str]
    content: Optional[str]
    url: str
    source: str
    published_at: datetime
    author: Optional[str] = None

    def get_full_text(self) -> str:
        """
        Get the full text content of the article.
        Combines title, description, and content.
        """
        parts = [self.title]

        if self.description:
            parts.append(self.description)

        if self.content:
            parts.append(self.content)

        return " ".join(parts)

    def __str__(self) -> str:
        return f"{self.title} - {self.source} ({self.published_at})"
