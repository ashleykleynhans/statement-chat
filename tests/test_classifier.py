"""Tests for classifier module."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.classifier import TransactionClassifier, ClassificationResult


@pytest.fixture
def classifier():
    """Create a classifier with test categories."""
    with patch('src.classifier.ollama.Client'):
        return TransactionClassifier(
            categories=["groceries", "fuel", "medical", "salary", "other"],
            classification_rules={
                "Woolworths": "groceries",
                "Shell": "fuel",
                "Dr ": "medical",
                "Salary": "salary",
            }
        )


class TestRulesBasedClassification:
    """Tests for rules-based classification."""

    def test_matches_exact_rule(self, classifier):
        """Test matching an exact rule."""
        result = classifier._check_rules("Woolworths Food")
        assert result == "groceries"

    def test_matches_case_insensitive(self, classifier):
        """Test rules are case-insensitive."""
        result = classifier._check_rules("woolworths food")
        assert result == "groceries"

    def test_no_match_returns_none(self, classifier):
        """Test no match returns None."""
        result = classifier._check_rules("Random Transaction")
        assert result is None

    def test_classify_uses_rules_first(self, classifier):
        """Test classify uses rules before LLM."""
        result = classifier.classify("Shell Fuel Station", -500)
        assert result.category == "fuel"
        assert result.confidence == "high"

    def test_medical_rule_with_space(self, classifier):
        """Test rule with space matches correctly."""
        result = classifier.classify("Dr Smith Medical", -200)
        assert result.category == "medical"


class TestLLMClassification:
    """Tests for LLM-based classification."""

    def test_classify_falls_back_to_llm(self, classifier):
        """Test classification falls back to LLM when no rule matches."""
        classifier._client.generate.return_value = {
            "response": '{"category": "other", "recipient_or_payer": "Test", "confidence": "medium"}'
        }

        result = classifier.classify("Random Transaction", -100)

        assert result.category == "other"
        classifier._client.generate.assert_called_once()

    def test_classify_handles_llm_error(self, classifier):
        """Test classification handles LLM errors gracefully."""
        classifier._client.generate.side_effect = Exception("Connection error")

        result = classifier.classify("Random Transaction", -100)

        assert result.category == "other"
        assert result.confidence == "low"


class TestResponseParsing:
    """Tests for LLM response parsing."""

    def test_parse_valid_json(self, classifier):
        """Test parsing valid JSON response."""
        response = '{"category": "groceries", "recipient_or_payer": "Woolworths", "confidence": "high"}'
        result = classifier._parse_response(response)

        assert result.category == "groceries"
        assert result.recipient_or_payer == "Woolworths"
        assert result.confidence == "high"

    def test_parse_json_with_markdown(self, classifier):
        """Test parsing JSON wrapped in markdown."""
        response = '```json\n{"category": "fuel", "recipient_or_payer": null, "confidence": "medium"}\n```'
        result = classifier._parse_response(response)

        assert result.category == "fuel"

    def test_parse_json_with_extra_text(self, classifier):
        """Test parsing JSON with surrounding text."""
        response = 'Here is the result: {"category": "medical", "recipient_or_payer": "Dr Smith", "confidence": "high"} Hope this helps!'
        result = classifier._parse_response(response)

        assert result.category == "medical"

    def test_parse_invalid_json(self, classifier):
        """Test parsing invalid JSON returns default."""
        response = "This is not valid JSON"
        result = classifier._parse_response(response)

        assert result.category == "other"
        assert result.confidence == "low"

    def test_parse_invalid_category(self, classifier):
        """Test parsing response with invalid category."""
        response = '{"category": "invalid_category", "recipient_or_payer": null, "confidence": "high"}'
        result = classifier._parse_response(response)

        assert result.category == "other"


class TestBatchClassification:
    """Tests for batch classification."""

    def test_classify_batch(self, classifier):
        """Test classifying multiple transactions."""
        transactions = [
            {"description": "Woolworths Food", "amount": -500},
            {"description": "Shell Fuel", "amount": -300},
            {"description": "Salary Payment", "amount": 10000},
        ]

        results = classifier.classify_batch(transactions)

        assert len(results) == 3
        assert results[0].category == "groceries"
        assert results[1].category == "fuel"
        assert results[2].category == "salary"


class TestConnectionCheck:
    """Tests for connection checking."""

    def test_check_connection_success(self, classifier):
        """Test successful connection check."""
        mock_model = MagicMock()
        mock_model.model = "llama3.2:latest"
        classifier._client.list.return_value = MagicMock(models=[mock_model])

        assert classifier.check_connection() is True

    def test_check_connection_model_not_found(self, classifier):
        """Test connection check when model not found."""
        mock_model = MagicMock()
        mock_model.model = "other_model:latest"
        classifier._client.list.return_value = MagicMock(models=[mock_model])

        assert classifier.check_connection() is False

    def test_check_connection_error(self, classifier):
        """Test connection check handles errors."""
        classifier._client.list.side_effect = Exception("Connection refused")

        assert classifier.check_connection() is False

    def test_get_available_models(self, classifier):
        """Test getting available models."""
        mock_model1 = MagicMock()
        mock_model1.model = "llama3.2:latest"
        mock_model2 = MagicMock()
        mock_model2.model = "mistral:latest"
        classifier._client.list.return_value = MagicMock(models=[mock_model1, mock_model2])

        models = classifier.get_available_models()

        assert "llama3.2:latest" in models
        assert "mistral:latest" in models

    def test_get_available_models_error(self, classifier):
        """Test getting models handles errors."""
        classifier._client.list.side_effect = Exception("Connection refused")

        models = classifier.get_available_models()

        assert models == []
