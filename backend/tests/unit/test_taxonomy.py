"""
Unit tests for the taxonomy classifier service.
Tests: code lookup, wildcard fallback, caching, all known categories.
"""
import pytest
from app.schemas.enums import FailureCause
from app.services.taxonomy import classify_failure_code, load_taxonomy, TaxonomyEntry


class TestTaxonomyLoader:

    def test_loads_without_error(self):
        taxonomy = load_taxonomy()
        assert len(taxonomy) > 5

    def test_wildcard_always_present(self):
        taxonomy = load_taxonomy()
        assert "*" in taxonomy

    def test_known_code_maps_correctly(self):
        entry = classify_failure_code("GATEWAY_ERROR")
        assert entry.internal_cause == FailureCause.TEMPORARY_FAILURE
        assert entry.retriable is True
        assert entry.suggested_wait_minutes == 30

    def test_insufficient_funds_mapped(self):
        entry = classify_failure_code("BAD_REQUEST_ERROR:INSUFFICIENT_BALANCE")
        assert entry.internal_cause == FailureCause.INSUFFICIENT_FUNDS
        assert entry.retriable is True
        assert entry.suggested_wait_minutes == 1440

    def test_risk_rejection_requires_human_review(self):
        entry = classify_failure_code("BAD_REQUEST_ERROR:CARD_STOLEN")
        assert entry.internal_cause == FailureCause.RISK_REJECTION
        assert entry.human_review is True
        assert entry.retriable is False

    def test_payment_method_failure_not_retriable(self):
        entry = classify_failure_code("BAD_REQUEST_ERROR:CARD_EXPIRED")
        assert entry.internal_cause == FailureCause.PAYMENT_METHOD_FAILURE
        assert entry.retriable is False

    def test_unknown_code_returns_wildcard(self):
        entry = classify_failure_code("SOME_TOTALLY_NEW_CODE_FROM_RAZORPAY")
        assert entry.internal_cause == FailureCause.UNKNOWN
        assert entry.llm_assist is True

    def test_none_code_returns_wildcard(self):
        entry = classify_failure_code(None)
        assert entry.internal_cause == FailureCause.UNKNOWN

    def test_customer_abandonment_classified(self):
        entry = classify_failure_code("BAD_REQUEST_ERROR:PAYMENT_CANCELLED")
        assert entry.internal_cause == FailureCause.CUSTOMER_ABANDONMENT
        assert entry.retriable is False

    def test_lru_cache_returns_same_object(self):
        """Taxonomy should be loaded once; repeated calls return cached dict."""
        t1 = load_taxonomy()
        t2 = load_taxonomy()
        assert t1 is t2   # same object — lru_cache working

    def test_taxonomy_entry_is_frozen(self):
        """TaxonomyEntry must be immutable."""
        entry = classify_failure_code("GATEWAY_ERROR")
        with pytest.raises((AttributeError, TypeError)):
            entry.retriable = False  # type: ignore
