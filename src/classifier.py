"""Transaction classifier using OpenAI-compatible LLM API."""

import json
import re
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class ClassificationResult:
    """Result of classifying a transaction."""
    category: str
    recipient_or_payer: str | None
    confidence: str  # "high", "medium", "low"


class TransactionClassifier:
    """Classify transactions using rules first, then LLM as fallback."""

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
        self._client = OpenAI(
            base_url=f"http://{host}:{port}/v1",
            api_key="lm-studio",
            timeout=30.0,
        )

    def _check_rules(self, description: str) -> str | None:
        """Check if description matches any classification rules.

        Patterns with spaces can match with or without spaces (for PDF extraction).
        Single-word patterns only match literally to avoid false positives
        (e.g., "Spur" should not match "pospurchase").
        Patterns with leading/trailing spaces are word boundary matches.
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
            elif ' ' in pattern:
                # Multi-word pattern: match with or without spaces (PDF flexibility)
                pattern_no_spaces = pattern_lower.replace(" ", "")
                if pattern_lower in desc_lower or pattern_no_spaces in desc_no_spaces:
                    return category
            else:
                # Single-word pattern: only match literally (avoid false positives)
                if pattern_lower in desc_lower:
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
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )

            content = response.choices[0].message.content
            # Strip reasoning model thinking tags
            content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL)
            return self._parse_response(content)
        except Exception as e:
            # Return default classification on error
            return ClassificationResult(
                category="other",
                recipient_or_payer=None,
                confidence="low"
            )

    def classify_rules_only(self, description: str, amount: float) -> ClassificationResult | None:
        """Classify using rules only, returning None if no rule matches."""
        rule_category = self._check_rules(description)
        if rule_category:
            return ClassificationResult(
                category=rule_category,
                recipient_or_payer=None,
                confidence="high"
            )
        return None

    def classify_batch_llm(
        self,
        transactions: list[dict],
        batch_size: int = 15
    ) -> list[ClassificationResult]:
        """Classify multiple transactions via LLM in batches.

        Sends multiple transactions per LLM call to reduce round-trips.

        Args:
            transactions: List of dicts with 'description' and 'amount' keys
            batch_size: Number of transactions per LLM call

        Returns:
            List of ClassificationResult objects in the same order
        """
        if not transactions:
            return []

        all_results: list[ClassificationResult] = []

        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            results = self._classify_llm_batch(batch)
            all_results.extend(results)

        return all_results

    def _classify_llm_batch(self, batch: list[dict]) -> list[ClassificationResult]:
        """Send a single batch of transactions to the LLM for classification."""
        lines = []
        for idx, tx in enumerate(batch):
            desc = tx.get("description", "")
            amount = tx.get("amount", 0)
            tx_type = "expense" if amount < 0 else "income"
            lines.append(f"{idx + 1}. \"{desc}\" | {tx_type} | {abs(amount):.2f}")

        transactions_text = "\n".join(lines)

        prompt = f"""Classify each bank transaction into a category.

Transactions:
{transactions_text}

Available categories: {', '.join(self.categories)}

Respond with ONLY a JSON array (no markdown, no explanation). One object per transaction, in order:
[{{"category": "...", "recipient_or_payer": "..." or null}}, ...]

Rules:
- category must be one from the available categories list
- recipient_or_payer should be the business/person name if identifiable, otherwise null
"""

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100 * len(batch),
            )

            content = response.choices[0].message.content
            # Strip reasoning model thinking tags
            content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL)
            return self._parse_batch_response(content, len(batch))
        except Exception:
            return [
                ClassificationResult(category="other", recipient_or_payer=None, confidence="low")
                for _ in batch
            ]

    def _parse_batch_response(self, response: str, expected_count: int) -> list[ClassificationResult]:
        """Parse a batch LLM response into a list of ClassificationResults."""
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:])
            response = response.strip()

        # Try to find JSON array
        bracket_start = response.find("[")
        bracket_end = response.rfind("]")
        if bracket_start != -1 and bracket_end != -1:
            response = response[bracket_start:bracket_end + 1]

        try:
            data = json.loads(response)
            if not isinstance(data, list):
                raise ValueError("Expected array")

            results = []
            for item in data:
                category = item.get("category", "other")
                if category not in self.categories:
                    category = "other"
                recipient = item.get("recipient_or_payer")
                if recipient == "null":
                    recipient = None
                results.append(ClassificationResult(
                    category=category,
                    recipient_or_payer=recipient,
                    confidence=item.get("confidence", "medium")
                ))

            # Pad if LLM returned fewer results than expected
            while len(results) < expected_count:
                results.append(ClassificationResult(
                    category="other", recipient_or_payer=None, confidence="low"
                ))

            return results[:expected_count]

        except (json.JSONDecodeError, ValueError):
            return [
                ClassificationResult(category="other", recipient_or_payer=None, confidence="low")
                for _ in range(expected_count)
            ]

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
        """Check if the LLM server is available."""
        try:
            response = self._client.models.list()
            model_ids = [m.id for m in response.data]
            return self.model in model_ids or len(model_ids) > 0
        except Exception:
            return False

    def get_available_models(self) -> list[str]:
        """Get list of available models."""
        try:
            response = self._client.models.list()
            return [m.id for m in response.data]
        except Exception:
            return []
