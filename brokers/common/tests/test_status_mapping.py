"""Comprehensive status mapping tests for broker status normalization.

These tests ensure that:
1. All known broker status strings map correctly to canonical OrderStatus
2. Unknown status strings are properly handled (strict mode raises, normal mode defaults)
3. Status mapping is consistent across all brokers
4. Order placement properly uses strict status mapping
"""

import pytest
from unittest.mock import Mock, patch

from domain import OrderStatus
from domain.status_mapper import (
    COMMON_STATUS_MAP,
    StatusMapperRegistry,
    UnmappedBrokerStatusError,
)


class TestStatusMapperRegistry:
    """Test the StatusMapperRegistry class functionality."""

    def test_normalize_known_status(self):
        """Test that known status strings normalize correctly."""
        test_cases = {
            "OPEN": OrderStatus.OPEN,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_CANCELLED,
            "EXECUTED": OrderStatus.FILLED,  # Common alias
            "COMPLETE": OrderStatus.FILLED,  # Common alias
            "TRADED": OrderStatus.FILLED,   # Common alias
            "TRANSIT": OrderStatus.OPEN,    # Common alias
            "PENDING": OrderStatus.OPEN,    # Common alias
        }
        
        for status_str, expected in test_cases.items():
            result = StatusMapperRegistry.normalize(status_str)
            assert result == expected, f"Expected {expected} for '{status_str}', got {result}"

    def test_normalize_case_insensitive(self):
        """Test that status normalization is case-insensitive."""
        assert StatusMapperRegistry.normalize("open") == OrderStatus.OPEN
        assert StatusMapperRegistry.normalize("OPEN") == OrderStatus.OPEN
        assert StatusMapperRegistry.normalize("Open") == OrderStatus.OPEN
        assert StatusMapperRegistry.normalize("OpEn") == OrderStatus.OPEN

    def test_normalize_with_whitespace(self):
        """Test that status normalization handles whitespace."""
        assert StatusMapperRegistry.normalize(" OPEN ") == OrderStatus.OPEN
        assert StatusMapperRegistry.normalize("  filled  ") == OrderStatus.FILLED

    def test_normalize_with_underscores(self):
        """Test that status normalization handles spaces and underscores."""
        assert StatusMapperRegistry.normalize("PARTIALLY FILLED") == OrderStatus.PARTIALLY_FILLED
        assert StatusMapperRegistry.normalize("PARTIALLY_FILLED") == OrderStatus.PARTIALLY_FILLED

    def test_normalize_unknown_status_returns_unknown(self):
        """Test that unknown status strings return UNKNOWN."""
        assert StatusMapperRegistry.normalize("INVALID_STATUS") == OrderStatus.UNKNOWN
        assert StatusMapperRegistry.normalize("UNKNOWN_STATUS") == OrderStatus.UNKNOWN
        assert StatusMapperRegistry.normalize("") == OrderStatus.UNKNOWN

    def test_normalize_strict_success(self):
        """Test that normalize_strict works for known statuses."""
        assert StatusMapperRegistry.normalize_strict("OPEN") == OrderStatus.OPEN
        assert StatusMapperRegistry.normalize_strict("FILLED") == OrderStatus.FILLED

    def test_normalize_strict_fails_on_unknown(self):
        """Test that normalize_strict raises for unknown statuses."""
        with pytest.raises(UnmappedBrokerStatusError) as exc_info:
            StatusMapperRegistry.normalize_strict("INVALID_STATUS")
        assert "INVALID_STATUS" in str(exc_info.value)

    def test_normalize_strict_empty_string(self):
        """Test that normalize_strict handles empty strings."""
        with pytest.raises(UnmappedBrokerStatusError) as exc_info:
            StatusMapperRegistry.normalize_strict("")
        assert "" in str(exc_info.value)

    def test_common_status_map_coverage(self):
        """Test that COMMON_STATUS_MAP has expected entries."""
        expected_statuses = {
            "OPEN", "FILLED", "CANCELLED", "REJECTED", "EXPIRED",
            "PARTIALLY_FILLED", "PARTIALLY_CANCELLED", "UNKNOWN",
            "EXECUTED", "COMPLETE", "TRADED", "TRANSIT", "PENDING"
        }
        map_statuses = set(COMMON_STATUS_MAP.keys())
        assert expected_statuses.issubset(map_statuses)


class TestDhanStatusMapping:
    """Test Dhan-specific status mapping."""

    def test_dhan_specific_statuses(self):
        """Test Dhan-specific status strings."""
        # Import Dhan status map
        from brokers.dhan.status_mapper import DHAN_STATUS_MAP
        
        dhan_specific = {
            "PLACED": OrderStatus.OPEN,
            "TRIGGERED": OrderStatus.OPEN,
            "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_CANCELLED,
        }
        
        for status_str, expected in dhan_specific.items():
            assert DHAN_STATUS_MAP[status_str] == expected

    def test_dhan_status_mapping_in_registry(self):
        """Test that Dhan statuses are registered in the global registry."""
        dhan_statuses = ["PLACED", "TRIGGERED", "PARTIALLY_CANCELLED"]
        for status in dhan_statuses:
            result = StatusMapperRegistry.normalize(status)
            assert result != OrderStatus.UNKNOWN


class TestUpstoxStatusMapping:
    """Test Upstox-specific status mapping."""

    def test_upstox_specific_statuses(self):
        """Test Upstox-specific status strings."""
        # Import Upstox status map
        from brokers.upstox.status_mapper import UPSTOX_STATUS_MAP
        
        upstox_specific = {
            "OPEN_ORDER": OrderStatus.OPEN,
            "TRIGGER_ORDER": OrderStatus.OPEN,
            "CANCEL_PENDING": OrderStatus.OPEN,
            "REJECTED_BY_BROKER": OrderStatus.REJECTED,
            "REJECTED_BY_EXCHANGE": OrderStatus.REJECTED,
            "MODIFIED": OrderStatus.OPEN,
            "MODIFIED_PENDING": OrderStatus.OPEN,
        }
        
        for status_str, expected in upstox_specific.items():
            assert UPSTOX_STATUS_MAP[status_str] == expected

    def test_upstox_status_mapping_in_registry(self):
        """Test that Upstox statuses are registered in the global registry."""
        upstox_statuses = ["OPEN_ORDER", "TRIGGER_ORDER", "REJECTED_BY_BROKER"]
        for status in upstox_statuses:
            result = StatusMapperRegistry.normalize(status)
            assert result != OrderStatus.UNKNOWN


class TestStrictStatusMappingIntegration:
    """Integration tests for strict status mapping in order placement."""

    def test_dhan_gateway_uses_strict_status_mapping(self):
        """Test that DhanGateway uses strict status mapping and fails on unknown statuses."""
        from brokers.dhan.gateway import BrokerGateway
        from brokers.dhan.exceptions import OrderError
        from unittest.mock import Mock, patch
        
        # Create a mock connection that returns an order with unknown status
        mock_conn = Mock()
        mock_order = Mock()
        mock_order.order_id = "test_order_123"
        mock_order.status.value = "UNKNOWN_STATUS"  # This should cause failure
        
        mock_conn.orders.place_order.return_value = mock_order
        
        gateway = BrokerGateway(mock_conn)
        
        # This should return a failed response due to unmapped status
        response = gateway.place_order("RELIANCE", "NSE", "BUY", 1)
        
        # Should not be successful due to unmapped status
        assert not response.success
        assert "UNMAPPED_STATUS" in response.message or "unmapped" in response.message.lower()
        assert response.error_code == "UNMAPPED_STATUS"

    def test_upstox_domain_mapper_uses_strict_status_mapping(self):
        """Test that UpstoxDomainMapper uses strict status mapping."""
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper, _wire_status_to_domain_status
        from domain.status_mapper import UnmappedBrokerStatusError
        
        # Test that known statuses work
        assert _wire_status_to_domain_status("OPEN") == OrderStatus.OPEN
        assert _wire_status_to_domain_status("FILLED") == OrderStatus.FILLED
        
        # Test that empty status defaults to OPEN (for backward compatibility)
        assert _wire_status_to_domain_status("") == OrderStatus.OPEN
        
        # Test that unknown statuses raise exceptions
        with pytest.raises(UnmappedBrokerStatusError):
            _wire_status_to_domain_status("INVALID_STATUS")

    def test_upstox_to_order_response_includes_status(self):
        """Test that to_order_response extracts and includes status."""
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        from domain import OrderResponse
        
        # Test with successful response including status
        payload = {
            "data": {
                "order_id": "test_123",
                "status": "OPEN"
            }
        }
        
        response = UpstoxDomainMapper.to_order_response(payload)
        assert response.success
        assert response.order_id == "test_123"
        assert response.status == OrderStatus.OPEN

    def test_upstox_to_order_response_handles_unknown_status(self):
        """Test that to_order_response handles unknown statuses gracefully."""
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        from domain import OrderResponse
        
        # Test with unknown status - should log but not fail
        payload = {
            "data": {
                "order_id": "test_456",
                "status": "UNKNOWN_STATUS"
            }
        }
        
        # Patch the logger at the module level where it's used
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            response = UpstoxDomainMapper.to_order_response(payload)
            
            # Should still return successful response but with OPEN status (fallback)
            assert response.success
            assert response.order_id == "test_456"
            assert response.status == OrderStatus.OPEN
            
            # Should have logged the error
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args
            assert "unmapped_order_status_in_response" in str(error_call)


class TestStatusMappingEdgeCases:
    """Edge case tests for status mapping."""

    def test_none_status(self):
        """Test handling of None status."""
        from brokers.upstox.mappers.domain_mapper import _wire_status_to_domain_status
        
        # Should handle None gracefully
        result = _wire_status_to_domain_status(None)
        assert result == OrderStatus.OPEN

    def test_non_string_status(self):
        """Test handling of non-string status values."""
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        
        # Should handle integer status codes
        payload = {
            "data": {
                "order_id": "test_789",
                "status": 123  # Non-string status
            }
        }
        
        response = UpstoxDomainMapper.to_order_response(payload)
        assert response.success
        # Should handle the conversion gracefully

    def test_mixed_case_with_spaces(self):
        """Test status strings with mixed case and spaces."""
        result = StatusMapperRegistry.normalize(" Partially Filled ")
        assert result == OrderStatus.PARTIALLY_FILLED

    def test_numerical_status_codes(self):
        """Test numerical status codes that might come from some brokers."""
        # Some brokers might use numerical codes - these should be handled
        # For now, they should fall back to UNKNOWN or raise in strict mode
        result = StatusMapperRegistry.normalize("1")
        # Should try to map to OrderStatus or fall back to UNKNOWN
        # This might need special handling in the mapper
        assert result in [OrderStatus.UNKNOWN, OrderStatus.OPEN]  # Depends on implementation


class TestStatusMappingPerformance:
    """Performance tests for status mapping."""

    def test_status_mapping_performance(self):
        """Test that status mapping is fast enough for high-frequency usage."""
        import time
        
        statuses = ["OPEN", "FILLED", "CANCELLED", "REJECTED", "PARTIALLY_FILLED", 
                   "PLACED", "TRIGGERED", "OPEN_ORDER", "REJECTED_BY_BROKER"]
        
        start_time = time.time()
        for _ in range(10000):  # 10k iterations
            for status in statuses:
                StatusMapperRegistry.normalize(status)
        
        elapsed = time.time() - start_time
        
        # Should handle 100k status mappings in < 1 second
        assert elapsed < 1.0, f"Status mapping too slow: {elapsed:.3f}s for 100k operations"

    def test_strict_mapping_performance(self):
        """Test that strict status mapping performance is acceptable."""
        import time
        
        statuses = ["OPEN", "FILLED", "CANCELLED"]  # Only known statuses for this test
        
        start_time = time.time()
        for _ in range(10000):  # 10k iterations
            for status in statuses:
                StatusMapperRegistry.normalize_strict(status)
        
        elapsed = time.time() - start_time
        
        # Should handle 30k strict mappings in < 1 second
        assert elapsed < 1.0, f"Strict status mapping too slow: {elapsed:.3f}s for 30k operations"


# Run tests with verbose output when executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])