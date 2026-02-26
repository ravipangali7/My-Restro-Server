"""
Shared order bill PDF generation. Used by waiter, owner, manager, and customer bill endpoints.
Content: restaurant logo, details, invoice number, date, customer, table, waiter, payment method,
items table (SN, Item Name, Price, Qty, Total), subtotal, tax, discount, service charge, grand total, status.
"""
from decimal import Decimal
from io import BytesIO
import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdf_canvas


def order_bill_pdf_bytes(order, title='Order Bill'):
    """
    Generate PDF bytes for an order bill/invoice.
    order: Order instance with select_related('table', 'restaurant', 'waiter__user', 'customer')
    and prefetch_related('items') with items select_related('product', 'combo_set').
    """
    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 40
    left = 50
    right_col = 350

    rest = getattr(order, 'restaurant', None)
    # Logo top-left (if available)
    if rest and getattr(rest, 'logo', None) and rest.logo:
        try:
            logo_path = rest.logo.path
            if os.path.isfile(logo_path):
                from reportlab.lib.utils import ImageReader
                img = ImageReader(logo_path)
                iw, ih = img.getSize()
                max_h = 44
                w = (iw * max_h / ih) if ih else max_h
                if w > 120:
                    w = 120
                c.drawImage(logo_path, left, y - max_h, width=w, height=max_h)
                y -= max_h + 8
        except Exception:
            pass

    c.setFont('Helvetica-Bold', 14)
    c.drawString(left, y, rest.name if rest else 'Restaurant')
    y -= 18
    c.setFont('Helvetica', 9)
    if rest and rest.address:
        for line in (rest.address or '').split('\n')[:3]:
            c.drawString(left, y, line[:80])
            y -= 12
    if rest and getattr(rest, 'email', None) and rest.email:
        c.drawString(left, y, rest.email)
        y -= 12
    if rest and rest.phone:
        c.drawString(left, y, rest.phone)
        y -= 14
    y -= 10

    # Invoice number and date (right-aligned or second column)
    invoice_number = f'INV-{order.id:06d}'
    c.setFont('Helvetica-Bold', 11)
    c.drawString(right_col, height - 40, f'Invoice: {invoice_number}')
    if order.created_at:
        c.setFont('Helvetica', 9)
        c.drawString(right_col, height - 54, f'Date: {order.created_at.strftime("%Y-%m-%d %H:%M")}')
    # Customer, Table, Waiter, Payment method
    info_y = height - 68
    c.setFont('Helvetica', 9)
    if getattr(order, 'customer', None) and order.customer:
        c.drawString(left, info_y, f'Customer: {order.customer.name}')
        info_y -= 12
    if order.table:
        c.drawString(left, info_y, f'Table: {order.table.name}')
    elif order.table_number:
        c.drawString(left, info_y, f'Table: {order.table_number}')
    else:
        c.drawString(left, info_y, 'Table: —')
    info_y -= 12
    waiter = getattr(order, 'waiter', None)
    if waiter and getattr(waiter, 'user', None):
        wn = (waiter.user.get_full_name() or waiter.user.username) if hasattr(waiter.user, 'get_full_name') else getattr(waiter.user, 'username', '')
        c.drawString(left, info_y, f'Waiter: {wn}')
    else:
        c.drawString(left, info_y, 'Waiter: —')
    info_y -= 12
    c.drawString(left, info_y, f'Payment: {order.payment_method or "—"}  |  Status: {order.payment_status or "pending"}')
    info_y -= 20
    y = min(y, info_y)

    # Table header: SN, Item Name, Price, Qty, Total
    c.setFont('Helvetica-Bold', 9)
    c.drawString(left, y, 'SN')
    c.drawString(left + 30, y, 'Item Name')
    c.drawString(280, y, 'Price')
    c.drawString(320, y, 'Qty')
    c.drawString(400, y, 'Total')
    y -= 14
    c.setFont('Helvetica', 9)

    for sn, item in enumerate(order.items.select_related('product', 'combo_set').all(), start=1):
        name = 'Item'
        if item.combo_set_id and item.combo_set:
            name = (item.combo_set.name or 'Item')[:35]
        elif item.product_id and item.product:
            name = (item.product.name or 'Item')[:35]
        c.drawString(left, y, str(sn))
        c.drawString(left + 30, y, name)
        c.drawString(280, y, f'Rs.{item.price}')
        c.drawString(320, y, str(item.quantity))
        c.drawString(400, y, f'Rs.{item.total}')
        y -= 12
        if y < 140:
            c.showPage()
            y = height - 40
            c.setFont('Helvetica', 9)

    y -= 8
    # Subtotal = sum of items
    subtotal = sum((i.total for i in order.items.all()), Decimal('0'))
    tax_percent = getattr(rest, 'tax_percent', None) if rest else None
    if tax_percent is not None and tax_percent > 0:
        tax = (subtotal * tax_percent / 100).quantize(Decimal('0.01'))
    else:
        tax = Decimal('0')
    service_charge = order.service_charge if order.service_charge is not None else Decimal('0')
    discount = order.discount if order.discount is not None else Decimal('0')

    c.drawString(right_col, y, f'Subtotal: Rs.{subtotal}')
    y -= 12
    if tax:
        c.drawString(right_col, y, f'Tax: Rs.{tax}')
        y -= 12
    if service_charge:
        c.drawString(right_col, y, f'Service charge: Rs.{service_charge}')
        y -= 12
    if discount:
        c.drawString(right_col, y, f'Discount: Rs.-{discount}')
        y -= 12
    c.setFont('Helvetica-Bold', 10)
    c.drawString(right_col, y, f'Grand Total: Rs.{order.total}')
    y -= 12
    c.setFont('Helvetica', 9)
    c.drawString(right_col, y, f'Status: {order.payment_status or "pending"}')

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
