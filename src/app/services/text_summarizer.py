from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch
from typing import List
from logging import getLogger
from app.models import NewsArticle

logger = getLogger(__name__)


class TextSummarizer:
    """
    Service for summarizing news articles using DistilBART.
    """

    def __init__(
        self,
        model_name: str = "sshleifer/distilbart-cnn-12-6",
        max_length: int = 150,
        min_length: int = 50
    ):
        """
        Initialize the text summarizer.

        Args:
            model_name: HuggingFace model name
            max_length: Maximum summary length in tokens
            min_length: Minimum summary length in tokens
        """
        self.model_name = model_name
        self.max_length = max_length
        self.min_length = min_length
        self.tokenizer = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def load_model(self):
        """Load the summarization model."""
        if self.model is not None:
            return

        logger.info(f"Loading summarization model: {self.model_name}")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                self.model_name
            )
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise

    def _clean_summary(self, summary: str) -> str:
        """
        Clean up common formatting issues in generated summaries.

        Args:
            summary: Raw summary text

        Returns:
            Cleaned summary text
        """
        import re

        # Fix spacing issues before punctuation
        summary = re.sub(r'\s+([.,!?;:])', r'\1', summary)

        # Fix missing spaces after punctuation
        summary = re.sub(r'([.,!?;:])([A-Z])', r'\1 \2', summary)

        # Fix concatenated words (e.g., "aNeutral" -> "a Neutral")
        # Look for lowercase letter followed by uppercase
        summary = re.sub(r'([a-z])([A-Z])', r'\1 \2', summary)

        # Fix lowercase letter followed by digit (e.g., "a55%" -> "a 55%")
        summary = re.sub(r'([a-z])(\d)', r'\1 \2', summary)

        # Fix specific common concatenations
        summary = re.sub(r'Neutralrating', 'Neutral rating', summary)
        summary = re.sub(r'Positiverating', 'Positive rating', summary)
        summary = re.sub(r'Negativerating', 'Negative rating', summary)

        # Remove multiple spaces
        summary = re.sub(r'\s+', ' ', summary)

        # Remove space before period at end
        summary = re.sub(r'\s+\.$', '.', summary)

        # Fix common brand names with incorrect spacing (do this last)
        summary = re.sub(r'\bi\s+Phone\b', 'iPhone', summary, flags=re.IGNORECASE)
        summary = re.sub(r'\bi\s+Pad\b', 'iPad', summary, flags=re.IGNORECASE)
        summary = re.sub(r'\bMac\s+Book\b', 'MacBook', summary, flags=re.IGNORECASE)

        return summary.strip()

    def summarize_text(self, text: str) -> str:
        """
        Summarize a single text.

        Args:
            text: Text to summarize

        Returns:
            Summary string
        """
        if not text or len(text.strip()) < 100:
            return text.strip()

        if self.model is None:
            self.load_model()

        try:
            # Prepare input
            inputs = self.tokenizer(
                text,
                max_length=1024,
                truncation=True,
                return_tensors="pt"
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Generate summary
            with torch.no_grad():
                summary_ids = self.model.generate(
                    inputs["input_ids"],
                    max_length=self.max_length,
                    min_length=self.min_length,
                    length_penalty=2.0,
                    num_beams=4,
                    early_stopping=True
                )

            # Decode summary
            summary = self.tokenizer.decode(
                summary_ids[0],
                skip_special_tokens=True
            )

            # Clean up the summary
            summary = self._clean_summary(summary)

            return summary.strip()

        except Exception as e:
            logger.error(f"Error summarizing text: {e}")
            # Return truncated text as fallback
            return text[:500] + "..."

    def summarize_articles(
        self,
        articles: List[NewsArticle],
        combine: bool = True
    ) -> str:
        """
        Summarize multiple articles.

        Args:
            articles: List of NewsArticle objects
            combine: If True, combine all articles and create one summary.
                    If False, summarize each article separately.

        Returns:
            Combined summary string
        """
        if not articles:
            return "No articles available for summarization."

        logger.info(f"Summarizing {len(articles)} articles")

        # Filter articles with content
        articles_with_content = [
            article for article in articles
            if article.content and len(article.content) > 100
        ]

        if not articles_with_content:
            # Fallback to titles and descriptions
            summaries = []
            for article in articles[:5]:  # Top 5 articles
                if article.title:
                    summaries.append(f"• {article.title}")
            return "\n".join(summaries) if summaries else "No content available."

        if combine:
            # Combine all article content
            combined_text = "\n\n".join([
                f"{article.title}: {article.content[:500]}"
                for article in articles_with_content[:5]  # Top 5
            ])

            summary = self.summarize_text(combined_text)
            logger.info(f"Generated combined summary: {len(summary)} chars")
            return summary
        else:
            # Summarize each article separately
            summaries = []
            for article in articles_with_content[:5]:  # Top 5
                article_summary = self.summarize_text(article.content)
                summaries.append(f"• {article.title}: {article_summary}")

            combined = "\n\n".join(summaries)
            logger.info(
                f"Generated {len(summaries)} individual summaries"
            )
            return combined

    def create_brief_summary(
        self,
        articles: List[NewsArticle],
        sentiment_label: str,
        sentiment_score: float
    ) -> str:
        """
        Create a brief summary including sentiment context.

        Args:
            articles: List of NewsArticle objects
            sentiment_label: Overall sentiment label
            sentiment_score: Overall sentiment score

        Returns:
            Brief summary with sentiment context
        """
        if not articles:
            return "No recent news available."

        # Get article summaries
        article_summary = self.summarize_articles(articles, combine=True)

        # Add sentiment context with adjusted thresholds
        sentiment_text = f"{sentiment_label.capitalize()}"
        if abs(sentiment_score) > 0.15:
            intensity = "strongly" if abs(sentiment_score) > 0.4 else "moderately"
            sentiment_text = f"{intensity} {sentiment_label}"

        # Combine
        brief = (
            f"Market sentiment is {sentiment_text} "
            f"(score: {sentiment_score:.2f}). "
            f"{article_summary}"
        )

        # Clean the final summary
        brief = self._clean_summary(brief)

        return brief
