"""
Notify order updates to customer via FCM.
Call after saving an order (create or update).
"""
import logging

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    'pending': 'Order received',
    'accepted': 'Order accepted',
    'running': 'Your order is being prepared',
    'ready': 'Your order is ready',
    'served': 'Order served',
    'rejected': 'Order rejected',
}


def notify_order_update(order):
    """
    Send order update to customer (FCM if token set).
    Call after order.save() in create/update views.
    """
    from core.fcm import send_fcm_to_token

    if order.fcm_token:
        title = 'Order update'
        body = STATUS_LABELS.get(order.status, f'Status: {order.status}')
        send_fcm_to_token(
            order.fcm_token,
            title,
            body,
            data={'order_id': str(order.id), 'status': order.status},
        )
