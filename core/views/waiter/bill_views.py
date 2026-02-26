"""Waiter: download order bill and QT (quotation) receipt as HTML or PDF."""
from decimal import Decimal

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404

from core.models import Order
from core.utils import get_waiter_staff_id
from core.bill_pdf import order_bill_pdf_bytes


def _order_html(o, title, filename_suffix):
    """Build HTML for order bill/invoice with invoice number, customer, waiter, payment method, SN, tax."""
    rows = []
    for sn, item in enumerate(o.items.select_related('product', 'combo_set').all(), start=1):
        name = 'Item'
        if item.combo_set_id and item.combo_set:
            name = item.combo_set.name or name
        elif item.product_id and item.product:
            name = item.product.name or name
        rows.append(
            f'<tr><td>{sn}</td><td>{name}</td><td>Rs.{item.price}</td><td>{item.quantity}</td><td>Rs.{item.total}</td></tr>'
        )
    items_html = '\n'.join(rows)
    table_info = f'<p>Table: {o.table.name if o.table else o.table_number or "—"}</p>'
    rest = o.restaurant
    rest_block = f'<div><strong>{rest.name}</strong><br/>{rest.address or ""}<br/>{getattr(rest, "email", "") or ""}<br/>{rest.phone or ""}</div>'
    subtotal = sum((i.total for i in o.items.all()), Decimal('0'))
    tax_percent = getattr(rest, 'tax_percent', None) if rest else None
    tax = (subtotal * tax_percent / 100).quantize(Decimal('0.01')) if tax_percent else Decimal('0')
    service_charge = o.service_charge if o.service_charge is not None else Decimal('0')
    discount = o.discount if o.discount is not None else Decimal('0')
    total_block = f'<div class="total">Subtotal: Rs.{subtotal}</div>'
    if tax:
        total_block += f'<div class="total">Tax: Rs.{tax}</div>'
    if service_charge:
        total_block += f'<div class="total">Service charge: Rs.{service_charge}</div>'
    if discount:
        total_block += f'<div class="total">Discount: Rs.-{discount}</div>'
    total_block += f'<div class="total">Grand Total: Rs.{o.total}</div>'
    total_block += f'<div class="total">Status: {o.payment_status or "pending"}</div>'
    waiter_name = '—'
    if o.waiter and getattr(o.waiter, 'user', None):
        u = o.waiter.user
        waiter_name = (u.get_full_name() or u.username) if hasattr(u, 'get_full_name') else getattr(u, 'username', '')
    customer_name = o.customer.name if getattr(o, 'customer', None) and o.customer else '—'
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:sans-serif;max-width:520px;margin:1rem auto;padding:1rem;}}
table{{width:100%;border-collapse:collapse;}} th,td{{text-align:left;padding:4px 8px;border-bottom:1px solid #eee;}}
th{{font-weight:600;}} .total{{font-weight:700;font-size:1.1em;margin-top:8px;}}
.invoice-meta{{margin:8px 0;}}
</style></head><body>
{rest_block}
<h2>{title}</h2>
<p><strong>Invoice: INV-{o.id:06d}</strong></p>
<p>Date: {o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else ""}</p>
<div class="invoice-meta">
<p>Customer: {customer_name}</p>
{table_info}
<p>Waiter: {waiter_name}</p>
<p>Payment: {o.payment_method or "—"} | Status: {o.payment_status or "pending"}</p>
</div>
<table>
<thead><tr><th>SN</th><th>Item Name</th><th>Price</th><th>Qty</th><th>Total</th></tr></thead>
<tbody>{items_html}</tbody>
</table>
{total_block}
</body></html>'''
    return html, filename_suffix


@require_http_methods(['GET'])
def waiter_order_bill(request, pk):
    """GET /api/waiter/orders/<id>/bill/ - Bill (HTML or ?format=pdf). Waiter must own order."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return HttpResponse('Forbidden', status=403)
    o = get_object_or_404(
        Order.objects.select_related('table', 'restaurant', 'waiter__user', 'customer').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    if o.waiter_id != staff_id:
        return HttpResponse('Forbidden', status=403)
    if request.GET.get('format') == 'pdf':
        pdf_bytes = order_bill_pdf_bytes(o, 'Order Bill')
        resp = HttpResponse(pdf_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="order-{o.id}-bill.pdf"'
        return resp
    html, _ = _order_html(o, 'Order Bill', 'bill')
    resp = HttpResponse(html, content_type='text/html; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="order-{o.id}-bill.html"'
    return resp


@require_http_methods(['GET'])
def waiter_order_qt_receipt(request, pk):
    """GET /api/waiter/orders/<id>/qt-receipt/ - QT receipt (HTML or ?format=pdf). Waiter must own order."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return HttpResponse('Forbidden', status=403)
    o = get_object_or_404(
        Order.objects.select_related('table', 'restaurant', 'waiter__user', 'customer').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    if o.waiter_id != staff_id:
        return HttpResponse('Forbidden', status=403)
    if request.GET.get('format') == 'pdf':
        pdf_bytes = order_bill_pdf_bytes(o, 'Quotation Receipt')
        resp = HttpResponse(pdf_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="order-{o.id}-qt-receipt.pdf"'
        return resp
    html, _ = _order_html(o, 'Quotation Receipt', 'qt-receipt')
    resp = HttpResponse(html, content_type='text/html; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="order-{o.id}-qt-receipt.html"'
    return resp
