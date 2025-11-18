from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from typing import List, Dict, Tuple
from logging import getLogger
from app.models import NewsArticle

logger = getLogger(__name__)


class SentimentAnalyzer:
    """
    Service for analyzing sentiment of financial news articles.
    Uses FinBERT model fine-tuned for financial sentiment.
    """

    def __init__(self, model_name: str = "ProsusAI/finbert"):
        """
        Initialize the sentiment analyzer.

        Args:
            model_name: HuggingFace model name
        """
        self.model_name = model_name
        self.tokenizer = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def load_model(self):
        """Load the sentiment analysis model."""
        if self.model is not None:
            return

        logger.info(f"Loading sentiment model: {self.model_name}")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name
            )
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise

    def analyze_text(self, text: str) -> Tuple[str, float, Dict[str, float]]:
        """
        Analyze sentiment of a single text.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (label, score, all_scores)
            - label: 'positive', 'negative', or 'neutral'
            - score: Confidence score (0-1)
            - all_scores: Dict with scores for all labels
        """
        if not text or len(text.strip()) < 10:
            return "neutral", 0.0, {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0
            }

        if self.model is None:
            self.load_model()

        try:
            # Truncate text to model's max length
            max_length = 512
            text = text[:max_length * 4]  # Rough char estimate

            # Tokenize
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=max_length,
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Get predictions
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(
                    outputs.logits,
                    dim=-1
                )

            # FinBERT outputs: [positive, negative, neutral]
            scores = predictions[0].cpu().numpy()
            labels = ["positive", "negative", "neutral"]

            # Get the label with highest score
            max_idx = scores.argmax()
            label = labels[max_idx]
            score = float(scores[max_idx])

            all_scores = {
                label: float(score)
                for label, score in zip(labels, scores)
            }

            return label, score, all_scores

        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return "neutral", 0.0, {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0
            }

    def analyze_article(
        self,
        article: NewsArticle
    ) -> Dict[str, any]:
        """
        Analyze sentiment of a news article.

        Args:
            article: NewsArticle object

        Returns:
            Dict with sentiment analysis results
        """
        # Use full content if available, otherwise use title + description
        text = article.get_full_text()

        label, score, all_scores = self.analyze_text(text)

        return {
            "label": label,
            "score": score,
            "all_scores": all_scores,
            "text_length": len(text)
        }

    def analyze_multiple(
        self,
        articles: List[NewsArticle]
    ) -> List[Dict[str, any]]:
        """
        Analyze sentiment for multiple articles.

        Args:
            articles: List of NewsArticle objects

        Returns:
            List of sentiment analysis results
        """
        logger.info(f"Analyzing sentiment for {len(articles)} articles")

        results = []
        for article in articles:
            result = self.analyze_article(article)
            results.append(result)

        # Log summary
        positive = sum(1 for r in results if r["label"] == "positive")
        negative = sum(1 for r in results if r["label"] == "negative")
        neutral = sum(1 for r in results if r["label"] == "neutral")

        logger.info(
            f"Sentiment summary - Positive: {positive}, "
            f"Negative: {negative}, Neutral: {neutral}"
        )

        return results

    def aggregate_sentiment(
        self,
        results: List[Dict[str, any]]
    ) -> Tuple[str, float]:
        """
        Aggregate sentiment from multiple articles.

        Args:
            results: List of sentiment analysis results

        Returns:
            Tuple of (overall_label, overall_score)
        """
        if not results:
            return "neutral", 0.0

        # Calculate weighted average
        total_positive = sum(r["all_scores"]["positive"] for r in results)
        total_negative = sum(r["all_scores"]["negative"] for r in results)
        total_neutral = sum(r["all_scores"]["neutral"] for r in results)

        count = len(results)
        avg_positive = total_positive / count
        avg_negative = total_negative / count
        avg_neutral = total_neutral / count

        # Determine overall sentiment
        scores = {
            "positive": avg_positive,
            "negative": avg_negative,
            "neutral": avg_neutral
        }

        # Calculate sentiment score: positive - negative (range: -1 to 1)
        sentiment_score = avg_positive - avg_negative

        # Determine label based on adjusted thresholds
        # Financial sentiment is typically close to 0, so use tighter bounds
        if sentiment_score >= 0.15:
            overall_label = "positive"
        elif sentiment_score <= -0.15:
            overall_label = "negative"
        else:
            overall_label = "neutral"

        return overall_label, sentiment_score
