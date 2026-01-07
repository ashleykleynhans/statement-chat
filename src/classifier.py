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
    """Classify transactions using rules first, then Ollama LLM as fallback."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        model: str = "llama3.2",
        categories: list[str] | None = None,
        classification_rules: dict[str, str] | None = None
    ):
        self.host = host
        self.port = port
        self.model = model
        self.categories = categories or [
            "doctor", "optician", "groceries", "garden_service",
            "dog_parlour", "domestic_worker", "education", "fuel",
            "utilities", "insurance", "entertainment", "transfer",
            "salary", "cellphone", "home_maintenance", "fees",
            "deposit", "savings", "eft_payment", "other"
        ]
        self.classification_rules = classification_rules or {}
        self._client = ollama.Client(host=f"http://{host}:{port}")

    def _check_rules(self, description: str) -> str | None:
        """Check if description matches any classification rules.

        Matches work with or without spaces to handle PDF extraction variations,
        but patterns with leading/trailing spaces (like ' Dr ') are treated as
        word boundaries and matched literally.
        """
        desc_lower = description.lower()
        desc_no_spaces = desc_lower.replace(" ", "")

        for pattern, category in self.classification_rules.items():
            pattern_lower = pattern.lower()

            # If pattern has leading or trailing spaces, those are significant
            # (used for word boundary matching like ' Dr ')
            has_boundary_spaces = pattern.startswith(' ') or pattern.endswith(' ')

            if has_boundary_spaces:
                # Only match with spaces preserved (word boundary matching)
                if pattern_lower in desc_lower:
                    return category
            else:
                # Match both with and without spaces (PDF extraction flexibility)
                pattern_no_spaces = pattern_lower.replace(" ", "")
                if pattern_lower in desc_lower or pattern_no_spaces in desc_no_spaces:
                    return category
        return None

    def classify(self, description: str, amount: float) -> ClassificationResult:
        """Classify a single transaction.

        Args:
            description: Transaction description from bank statement
            amount: Transaction amount (negative for debits)

        Returns:
            ClassificationResult with category and extracted recipient
        """
        # First, check rules-based classification
        rule_category = self._check_rules(description)
        if rule_category:
            return ClassificationResult(
                category=rule_category,
                recipient_or_payer=None,
                confidence="high"
            )

        # Fall back to LLM classification
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

            # Convert string "null" to Python None
            recipient = data.get("recipient_or_payer")
            if recipient == "null":
                recipient = None

            return ClassificationResult(
                category=category,
                recipient_or_payer=recipient,
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
            response = self._client.list()
            model_names = [m.model.split(":")[0] for m in response.models]
            return self.model.split(":")[0] in model_names
        except Exception:
            return False

    def get_available_models(self) -> list[str]:
        """Get list of available Ollama models."""
        try:
            response = self._client.list()
            return [m.model for m in response.models]
        except Exception:
            return []
