"""
Shared invoice payload builder. Used by owner, manager, waiter, and customer order-detail
and bill endpoints so the frontend receives a consistent invoice-ready shape.
All data comes from relational queries (Order with select_related/prefetch_related).
"""
from decimal import Decimal


def get_invoice_extras(order):
    """
    Build extra fields for invoice display from an Order instance.
    Expects order to have: select_related('restaurant', 'table', 'waiter__user', 'customer')
    and prefetch_related('items') with items having product/combo_set for names.
    Returns dict with: restaurant_logo, restaurant_email, invoice_number, subtotal, tax, grand_total.
    """
    rest = getattr(order, 'restaurant', None)
    subtotal = sum((item.total for item in order.items.all()), Decimal('0'))
    tax_percent = getattr(rest, 'tax_percent', None) if rest else None
    if tax_percent is not None and tax_percent > 0:
        tax = (subtotal * tax_percent / 100).quantize(Decimal('0.01'))
    else:
        tax = Decimal('0')
    return {
        'restaurant_logo': rest.logo.url if rest and getattr(rest, 'logo', None) and rest.logo else None,
        'restaurant_email': getattr(rest, 'email', None) or '' if rest else '',
        'invoice_number': f'INV-{order.id:06d}',
        'subtotal': str(subtotal),
        'tax': str(tax),
        'grand_total': str(order.total),
    }


def order_to_invoice_payload(order, request=None):
    """
    Build full invoice payload from an Order (for API response or PDF).
    order must be loaded with:
      select_related('restaurant', 'table', 'waiter__user', 'customer')
      prefetch_related('items') and items with select_related('product', 'combo_set')
    request is optional (for building absolute logo URL in waiter/customer views).
    Returns dict with all keys needed for InvoiceView: restaurant_*, invoice_number, date,
    customer_name, table_number, table_name, waiter_name, payment_method, payment_status,
    items (list of {id, sn, item_name, price, quantity, total}), subtotal, tax, discount,
    service_charge, grand_total.
    """
    rest = getattr(order, 'restaurant', None)
    extras = get_invoice_extras(order)
    waiter = getattr(order, 'waiter', None)
    waiter_name = None
    if waiter and getattr(waiter, 'user', None):
        u = waiter.user
        waiter_name = (u.get_full_name() or u.username) if hasattr(u, 'get_full_name') else getattr(u, 'username', '')
    items_list = []
    for sn, i in enumerate(order.items.select_related('product', 'combo_set').all(), start=1):
        item_name = 'Item'
        if i.combo_set_id and i.combo_set:
            item_name = i.combo_set.name or item_name
        elif i.product_id and i.product:
            item_name = i.product.name or item_name
        items_list.append({
            'id': i.id,
            'sn': sn,
            'item_name': item_name,
            'product_name': item_name,
            'price': str(i.price),
            'quantity': str(i.quantity),
            'total': str(i.total),
        })
    return {
        'restaurant_name': rest.name if rest else None,
        'restaurant_address': getattr(rest, 'address', None) or '' if rest else '',
        'restaurant_phone': getattr(rest, 'phone', None) or '' if rest else '',
        'restaurant_email': extras['restaurant_email'],
        'restaurant_logo': extras['restaurant_logo'],
        'invoice_number': extras['invoice_number'],
        'date': order.created_at.isoformat() if order.created_at else None,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'customer_name': order.customer.name if getattr(order, 'customer', None) and order.customer else None,
        'table_number': order.table_number or (order.table.name if order.table else '') or '',
        'table_name': order.table.name if order.table else None,
        'waiter_name': waiter_name,
        'payment_method': order.payment_method or '',
        'payment_status': order.payment_status or 'pending',
        'items': items_list,
        'subtotal': extras['subtotal'],
        'tax': extras['tax'],
        'discount': str(order.discount) if order.discount is not None else '0',
        'service_charge': str(order.service_charge) if order.service_charge is not None else '0',
        'grand_total': extras['grand_total'],
        'total': extras['grand_total'],
    }
