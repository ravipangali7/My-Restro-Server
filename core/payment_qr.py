"""
Esewa payment QR generation for orders.
Uses qrcode library; payload format can be updated per Esewa docs.
"""
import io
import json
import qrcode
from decimal import Decimal


def generate_esewa_qr_png(order, amount_override=None):
    """
    Generate PNG bytes for an Esewa payment QR for the given order.
    Uses restaurant's esewa_merchant_id when set; otherwise encodes amount + ref only
    so the endpoint still returns a valid QR (avoids 400 when Esewa is not configured).
    Returns (png_bytes, None) on success or (None, error_message) on failure.
    """
    if not order or not order.restaurant_id:
        return None, 'Invalid order'
    restaurant = order.restaurant
    amount = amount_override
    if amount is None:
        amount = order.total
    if amount is None or (isinstance(amount, Decimal) and amount <= 0):
        return None, 'Invalid amount'
    if isinstance(amount, Decimal):
        amount = str(amount)
    else:
        amount = str(amount)
    merchant_id = (getattr(restaurant, 'esewa_merchant_id', None) or '').strip()
    if merchant_id:
        payload = json.dumps({
            'merchant_id': merchant_id,
            'amount': amount,
            'ref': str(order.id),
        })
    else:
        # No Esewa ID configured: still return a QR with amount + order ref so page loads (no 400)
        payload = json.dumps({
            'amount': amount,
            'ref': str(order.id),
            'message': 'Configure Esewa in restaurant settings for scan-to-pay',
        })
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue(), None
