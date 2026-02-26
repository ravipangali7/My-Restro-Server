"""
WebSocket consumer for live delivery tracking. Clients subscribe by order_id; server pushes location/status updates.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework.authtoken.models import Token
from core.models import Delivery, Order, CustomerToken

logger = logging.getLogger(__name__)


def _get_user_from_token(token_key):
    """Resolve User from DRF Token. Returns (user, None) or (None, error)."""
    try:
        token = Token.objects.select_related('user').get(key=token_key)
        return token.user, None
    except Token.DoesNotExist:
        return None, 'Invalid token'


def _get_customer_from_token(token_key):
    """Resolve Customer from CustomerToken. Returns (customer, None) or (None, error)."""
    try:
        token = CustomerToken.objects.select_related('customer').get(key=token_key)
        return token.customer, None
    except CustomerToken.DoesNotExist:
        return None, 'Invalid token'


def _can_access_delivery(order_id, user=None, customer=None):
    """
    Return True if the given user or customer can access this delivery.
    - Customer: order must belong to customer.
    - Staff (owner/manager/waiter): order's restaurant must be in their scope (get_restaurant_ids).
    """
    try:
        order = Order.objects.select_related('restaurant').get(pk=order_id)
    except Order.DoesNotExist:
        return False
    if customer is not None:
        return order.customer_id == customer.id
    if user is not None:
        from core.utils import get_restaurant_ids
        # Build a minimal request-like object with user
        class Req:
            pass
        req = Req()
        req.user = user
        rid = get_restaurant_ids(req)
        if not rid and not getattr(user, 'is_superuser', False):
            return False
        return order.restaurant_id in rid if rid else True
    return False


@database_sync_to_async
def authenticate_and_check_access(order_id, token_key, is_customer=False):
    """Resolve token to user/customer and check if they can access this delivery."""
    if is_customer:
        customer, err = _get_customer_from_token(token_key)
        if err:
            return False, err
        if not _can_access_delivery(order_id, customer=customer):
            return False, 'Forbidden'
        return True, None
    user, err = _get_user_from_token(token_key)
    if err:
        return False, err
    if not _can_access_delivery(order_id, user=user):
        return False, 'Forbidden'
    return True, None


class TrackingConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket for delivery tracking. URL: /ws/tracking/<order_id>/?token=...&mode=user|customer"""

    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs'].get('order_id')
        if not self.order_id:
            await self.close(code=4000)
            return
        query = self.scope.get('query_string', b'').decode()
        params = {}
        for part in query.split('&'):
            if '=' in part:
                k, v = part.split('=', 1)
                params[k] = v
        token = params.get('token')
        mode = params.get('mode', 'user')  # 'user' | 'customer'
        if not token:
            await self.close(code=4001)
            return
        ok, err = await authenticate_and_check_access(
            int(self.order_id), token, is_customer=(mode == 'customer')
        )
        if not ok:
            await self.close(code=4003)
            return
        self.group_name = f'tracking_delivery_{self.order_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def tracking_update(self, event):
        """Handle broadcast from backend: send payload to client."""
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps(payload))
