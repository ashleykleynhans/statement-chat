"""Tests for classifier module."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.classifier import TransactionClassifier, ClassificationResult


@pytest.fixture
def classifier():
    """Create a classifier with test categories."""
    with patch('src.classifier.OpenAI'):
        return TransactionClassifier(
            categories=["groceries", "fuel", "medical", "salary", "subscriptions", "other"],
            classification_rules={
                "Woolworths": "groceries",
                "Shell": "fuel",
                "Dr ": "medical",
                "Salary": "salary",
                "Google One": "subscriptions",  # Multi-word pattern
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

    def test_matches_without_spaces_in_description(self, classifier):
        """Test rules match when description has no spaces (PDF extraction issue)."""
        # Description without spaces should still match "Woolworths" rule
        result = classifier._check_rules("POSPurchaseWoolworthsFood")
        assert result == "groceries"

    def test_matches_without_spaces_in_pattern(self, classifier):
        """Test rules match when pattern would have no spaces in description."""
        # "Shell" should match "ShellFuelStation" (no spaces)
        result = classifier._check_rules("ShellFuelStation")
        assert result == "fuel"

    def test_boundary_space_pattern_not_match_substring(self, classifier):
        """Test patterns with boundary spaces don't match substrings."""
        # " Dr " should NOT match "Withdrawal" even though it contains "dr"
        result = classifier._check_rules("Paypal Withdrawal")
        assert result is None  # Should not match medical

    def test_boundary_space_pattern_matches_word(self, classifier):
        """Test patterns with boundary spaces match actual words."""
        # " Dr " should match " Dr Smith"
        result = classifier._check_rules("Payment Dr Smith Medical")
        assert result == "medical"

    def test_multiword_pattern_matches_without_spaces(self, classifier):
        """Test multi-word patterns match when description has no spaces (PDF extraction)."""
        # "Google One" pattern should match "GoogleOne" in description
        result = classifier._check_rules("POSPurchaseGoogleOne12345")
        assert result == "subscriptions"

    def test_multiword_pattern_matches_with_spaces(self, classifier):
        """Test multi-word patterns match normally with spaces."""
        result = classifier._check_rules("POS Purchase Google One 12345")
        assert result == "subscriptions"


class TestLLMClassification:
    """Tests for LLM-based classification."""

    def test_classify_falls_back_to_llm(self, classifier):
        """Test classification falls back to LLM when no rule matches."""
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(
            content='{"category": "other", "recipient_or_payer": "Test", "confidence": "medium"}'
        ))]
        classifier._client.chat.completions.create.return_value = mock_response

        result = classifier.classify("Random Transaction", -100)

        assert result.category == "other"
        classifier._client.chat.completions.create.assert_called_once()

    def test_classify_handles_llm_error(self, classifier):
        """Test classification handles LLM errors gracefully."""
        classifier._client.chat.completions.create.side_effect = Exception("Connection error")

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

    def test_parse_null_string_as_recipient(self, classifier):
        """Test parsing 'null' string for recipient converts to None."""
        response = '{"category": "fuel", "recipient_or_payer": "null", "confidence": "high"}'
        result = classifier._parse_response(response)

        assert result.category == "fuel"
        assert result.recipient_or_payer is None


class TestRulesOnlyClassification:
    """Tests for classify_rules_only method."""

    def test_returns_result_when_rule_matches(self, classifier):
        """Test returns ClassificationResult when rule matches."""
        result = classifier.classify_rules_only("Woolworths Food", -500)
        assert result is not None
        assert result.category == "groceries"
        assert result.confidence == "high"

    def test_returns_none_when_no_rule_matches(self, classifier):
        """Test returns None when no rule matches."""
        result = classifier.classify_rules_only("Random Transaction", -100)
        assert result is None


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


class TestBatchLLMClassification:
    """Tests for batch LLM classification."""

    def test_batch_llm_empty_list(self, classifier):
        """Test batch LLM with empty list returns empty."""
        results = classifier.classify_batch_llm([])
        assert results == []

    def test_batch_llm_success(self, classifier):
        """Test batch LLM classifies multiple transactions in one call."""
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(
            content='[{"category": "groceries", "recipient_or_payer": "Shop"}, {"category": "fuel", "recipient_or_payer": null}]'
        ))]
        classifier._client.chat.completions.create.return_value = mock_response

        transactions = [
            {"description": "Some shop", "amount": -500},
            {"description": "Gas station", "amount": -300},
        ]
        results = classifier.classify_batch_llm(transactions)

        assert len(results) == 2
        assert results[0].category == "groceries"
        assert results[0].recipient_or_payer == "Shop"
        assert results[1].category == "fuel"
        assert results[1].recipient_or_payer is None
        # Should be a single LLM call for the batch
        assert classifier._client.chat.completions.create.call_count == 1

    def test_batch_llm_handles_error(self, classifier):
        """Test batch LLM returns defaults on error."""
        classifier._client.chat.completions.create.side_effect = Exception("Connection error")

        transactions = [
            {"description": "Shop", "amount": -500},
            {"description": "Gas", "amount": -300},
        ]
        results = classifier.classify_batch_llm(transactions)

        assert len(results) == 2
        assert all(r.category == "other" for r in results)
        assert all(r.confidence == "low" for r in results)

    def test_batch_llm_splits_large_batches(self, classifier):
        """Test large lists are split into multiple LLM calls."""
        mock_response = Mock()
        # Return valid response for each batch
        mock_response.choices = [Mock(message=Mock(
            content='[' + ','.join(['{"category": "other", "recipient_or_payer": null}'] * 15) + ']'
        ))]
        classifier._client.chat.completions.create.return_value = mock_response

        transactions = [{"description": f"Tx {i}", "amount": -100} for i in range(20)]
        results = classifier.classify_batch_llm(transactions, batch_size=15)

        assert len(results) == 20
        # Should be 2 LLM calls: 15 + 5
        assert classifier._client.chat.completions.create.call_count == 2


class TestBatchResponseParsing:
    """Tests for _parse_batch_response."""

    def test_parse_valid_array(self, classifier):
        """Test parsing valid JSON array."""
        response = '[{"category": "groceries", "recipient_or_payer": "Shop"}, {"category": "fuel", "recipient_or_payer": null}]'
        results = classifier._parse_batch_response(response, 2)

        assert len(results) == 2
        assert results[0].category == "groceries"
        assert results[1].category == "fuel"

    def test_parse_array_with_markdown(self, classifier):
        """Test parsing JSON array wrapped in markdown."""
        response = '```json\n[{"category": "fuel", "recipient_or_payer": null}]\n```'
        results = classifier._parse_batch_response(response, 1)

        assert len(results) == 1
        assert results[0].category == "fuel"

    def test_parse_invalid_json(self, classifier):
        """Test parsing invalid JSON returns defaults."""
        results = classifier._parse_batch_response("not json", 3)

        assert len(results) == 3
        assert all(r.category == "other" for r in results)

    def test_parse_pads_missing_results(self, classifier):
        """Test pads with defaults when LLM returns fewer than expected."""
        response = '[{"category": "fuel", "recipient_or_payer": null}]'
        results = classifier._parse_batch_response(response, 3)

        assert len(results) == 3
        assert results[0].category == "fuel"
        assert results[1].category == "other"
        assert results[2].category == "other"

    def test_parse_truncates_extra_results(self, classifier):
        """Test truncates when LLM returns more than expected."""
        response = '[{"category": "fuel", "recipient_or_payer": null}, {"category": "groceries", "recipient_or_payer": null}, {"category": "other", "recipient_or_payer": null}]'
        results = classifier._parse_batch_response(response, 2)

        assert len(results) == 2

    def test_parse_invalid_category_defaults_to_other(self, classifier):
        """Test invalid category in batch response defaults to other."""
        response = '[{"category": "invalid_cat", "recipient_or_payer": null}]'
        results = classifier._parse_batch_response(response, 1)

        assert results[0].category == "other"

    def test_parse_null_string_recipient(self, classifier):
        """Test string 'null' for recipient converts to None."""
        response = '[{"category": "fuel", "recipient_or_payer": "null"}]'
        results = classifier._parse_batch_response(response, 1)

        assert results[0].recipient_or_payer is None

    def test_parse_non_array_json(self, classifier):
        """Test non-array JSON returns defaults."""
        response = '{"category": "fuel"}'
        results = classifier._parse_batch_response(response, 2)

        assert len(results) == 2
        assert all(r.category == "other" for r in results)


class TestConnectionCheck:
    """Tests for connection checking."""

    def test_check_connection_success(self, classifier):
        """Test successful connection check."""
        mock_model = MagicMock()
        mock_model.id = "llama3.2"
        classifier._client.models.list.return_value = MagicMock(data=[mock_model])

        assert classifier.check_connection() is True

    def test_check_connection_model_not_found(self, classifier):
        """Test connection check when model not found but server available."""
        mock_model = MagicMock()
        mock_model.id = "other_model"
        classifier._client.models.list.return_value = MagicMock(data=[mock_model])

        # Should still return True if any model is available
        assert classifier.check_connection() is True

    def test_check_connection_error(self, classifier):
        """Test connection check handles errors."""
        classifier._client.models.list.side_effect = Exception("Connection refused")

        assert classifier.check_connection() is False

    def test_get_available_models(self, classifier):
        """Test getting available models."""
        mock_model1 = MagicMock()
        mock_model1.id = "llama3.2"
        mock_model2 = MagicMock()
        mock_model2.id = "mistral"
        classifier._client.models.list.return_value = MagicMock(data=[mock_model1, mock_model2])

        models = classifier.get_available_models()

        assert "llama3.2" in models
        assert "mistral" in models

    def test_get_available_models_error(self, classifier):
        """Test getting models handles errors."""
        classifier._client.models.list.side_effect = Exception("Connection refused")

        models = classifier.get_available_models()

        assert models == []
