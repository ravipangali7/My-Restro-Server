"""
Third-party delivery providers (Pathao, Yango). Placeholder/mock implementations.
Implement real API calls when keys are configured.
"""
from typing import Optional, Dict, Any
from decimal import Decimal


class BaseDeliveryProvider:
    """Base interface for request_ride and get_ride_status."""

    def request_ride(
        self,
        pickup_lat: Decimal,
        pickup_lon: Decimal,
        delivery_lat: Decimal,
        delivery_lon: Decimal,
        order_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Request a ride. Returns dict with request_id, status, optional rider info."""
        raise NotImplementedError

    def get_ride_status(self, request_id: str) -> Dict[str, Any]:
        """Get current status: status, rider_name, rider_phone, rider_lat, rider_lon."""
        raise NotImplementedError


class PathaoProvider(BaseDeliveryProvider):
    """Pathao integration. Mock until PATHAO_API_KEY etc. are set."""

    def __init__(self):
        import os
        self.api_key = os.environ.get('PATHAO_API_KEY', '').strip()
        self.enabled = bool(self.api_key)

    def request_ride(
        self,
        pickup_lat: Decimal,
        pickup_lon: Decimal,
        delivery_lat: Decimal,
        delivery_lon: Decimal,
        order_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {
                'request_id': f'mock_pathao_{order_id}',
                'status': 'pending',
                'message': 'Pathao integration not configured; using mock.',
            }
        # TODO: call Pathao API when implemented
        return {
            'request_id': f'mock_pathao_{order_id}',
            'status': 'pending',
        }

    def get_ride_status(self, request_id: str) -> Dict[str, Any]:
        if not self.enabled:
            return {'status': 'pending', 'request_id': request_id}
        # TODO: call Pathao API
        return {'status': 'pending', 'request_id': request_id}


class YangoProvider(BaseDeliveryProvider):
    """Yango integration. Mock until YANGO_* env are set."""

    def __init__(self):
        import os
        self.api_key = os.environ.get('YANGO_API_KEY', '').strip()
        self.enabled = bool(self.api_key)

    def request_ride(
        self,
        pickup_lat: Decimal,
        pickup_lon: Decimal,
        delivery_lat: Decimal,
        delivery_lon: Decimal,
        order_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {
                'request_id': f'mock_yango_{order_id}',
                'status': 'pending',
                'message': 'Yango integration not configured; using mock.',
            }
        # TODO: call Yango API when implemented
        return {
            'request_id': f'mock_yango_{order_id}',
            'status': 'pending',
        }

    def get_ride_status(self, request_id: str) -> Dict[str, Any]:
        if not self.enabled:
            return {'status': 'pending', 'request_id': request_id}
        return {'status': 'pending', 'request_id': request_id}


def get_provider(source: str) -> Optional[BaseDeliveryProvider]:
    """Return provider instance for 'pathao' or 'yango', else None."""
    if source == 'pathao':
        return PathaoProvider()
    if source == 'yango':
        return YangoProvider()
    return None
