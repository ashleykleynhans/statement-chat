"""Transaction classifier using Ollama LLM."""

import json
import re
from dataclasses import dataclass

import ollama


@dataclass
class ClassificationResult:
    """Result of classifying a transaction."""
    category: str
    recipient_or_payer: str | None
    confidence: str  # "high", "medium", "low"


class TransactionClassifier:
    """Classify transactions using a local Ollama LLM."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        model: str = "llama3.2",
        categories: list[str] | None = None
    ):
        self.host = host
        self.port = port
        self.model = model
        self.categories = categories or [
            "doctor", "optician", "groceries", "garden_service",
            "dog_parlour", "domestic_worker", "education", "fuel",
            "utilities", "insurance", "entertainment", "transfer",
            "salary", "other"
        ]
        self._client = ollama.Client(host=f"http://{host}:{port}")

    def classify(self, description: str, amount: float) -> ClassificationResult:
        """Classify a single transaction.

        Args:
            description: Transaction description from bank statement
            amount: Transaction amount (negative for debits)

        Returns:
            ClassificationResult with category and extracted recipient
        """
        transaction_type = "payment/expense" if amount < 0 else "income/deposit"

        prompt = f"""Analyze this bank transaction and classify it.

Transaction description: {description}
Transaction type: {transaction_type}
Amount: {abs(amount):.2f}

Available categories: {', '.join(self.categories)}

Respond with ONLY a JSON object (no markdown, no explanation) in this exact format:
{{"category": "category_name", "recipient_or_payer": "name or null", "confidence": "high/medium/low"}}

Rules:
- category must be one from the available categories list
- recipient_or_payer should be the business/person name if identifiable, otherwise null
- confidence: high if category is obvious, medium if reasonable guess, low if uncertain
"""

        try:
            response = self._client.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": 0.1}
            )

            return self._parse_response(response["response"])
        except Exception as e:
            # Return default classification on error
            return ClassificationResult(
                category="other",
                recipient_or_payer=None,
                confidence="low"
            )

    def classify_batch(
        self,
        transactions: list[dict]
    ) -> list[ClassificationResult]:
        """Classify multiple transactions.

        Args:
            transactions: List of dicts with 'description' and 'amount' keys

        Returns:
            List of ClassificationResult objects
        """
        results = []
        for tx in transactions:
            result = self.classify(
                tx.get("description", ""),
                tx.get("amount", 0)
            )
            results.append(result)
        return results

    def _parse_response(self, response: str) -> ClassificationResult:
        """Parse LLM response into ClassificationResult."""
        # Try to extract JSON from response
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            response = response.strip()

        # Try to find JSON object
        json_match = re.search(r"\{[^}]+\}", response)
        if json_match:
            response = json_match.group()

        try:
            data = json.loads(response)

            category = data.get("category", "other")
            # Validate category is in our list
            if category not in self.categories:
                category = "other"

            return ClassificationResult(
                category=category,
                recipient_or_payer=data.get("recipient_or_payer"),
                confidence=data.get("confidence", "medium")
            )
        except json.JSONDecodeError:
            return ClassificationResult(
                category="other",
                recipient_or_payer=None,
                confidence="low"
            )

    def check_connection(self) -> bool:
        """Check if Ollama is available and the model is loaded."""
        try:
            models = self._client.list()
            model_names = [m["name"].split(":")[0] for m in models.get("models", [])]
            return self.model.split(":")[0] in model_names
        except Exception:
            return False

    def get_available_models(self) -> list[str]:
        """Get list of available Ollama models."""
        try:
            models = self._client.list()
            return [m["name"] for m in models.get("models", [])]
        except Exception:
            return []
