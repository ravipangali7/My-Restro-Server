"""Owner reports: Sales, Purchase, Expense, Paid/Received, Stock Movement. Scoped to owner's restaurants."""
import csv
import io
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from datetime import datetime
from django.utils import timezone

from core.models import Order, OrderStatus, Purchase, Expenses, PaidRecord, ReceivedRecord, StockLog, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@auth_required
@require_http_methods(['GET'])
def owner_reports(request):
    """GET /owner/reports/?date_from=&date_to=&group_by=day|month|year&restaurant_id=
    Returns: sales_report, purchase_report, expense_report, paid_received_report, stock_movement, restaurants (for filter dropdown).
    """
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({
            'sales_report': [],
            'purchase_report': [],
            'expense_report': [],
            'paid_received_report': {'paid': [], 'received': []},
            'stock_movement': [],
            'restaurants': [],
            'filters': {},
        })

    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    group_by = (request.GET.get('group_by') or 'day').lower()
    if group_by not in ('day', 'month', 'year'):
        group_by = 'day'
    restaurant_id = request.GET.get('restaurant_id')
    try:
        filter_rid = int(restaurant_id) if restaurant_id else None
    except (TypeError, ValueError):
        filter_rid = None
    if filter_rid and filter_rid not in rid and not getattr(request.user, 'is_superuser', False):
        filter_rid = None
    scope_rid = [filter_rid] if filter_rid else rid

    if group_by == 'month':
        annotate_fn = TruncMonth('created_at')
        key_name = 'month'
    elif group_by == 'year':
        annotate_fn = TruncYear('created_at')
        key_name = 'year'
    else:
        annotate_fn = TruncDate('created_at')
        key_name = 'day'

    def _series(qs, date_field, value_attr, value_agg='Sum'):
        qs = qs.filter(restaurant_id__in=scope_rid)
        if date_from:
            qs = qs.filter(**{f'{date_field}__date__gte': date_from})
        if date_to:
            qs = qs.filter(**{f'{date_field}__date__lte': date_to})
        agg = Sum(value_attr) if value_agg == 'Sum' else Sum(value_attr)
        annotated = qs.annotate(**{key_name: annotate_fn}).values(key_name).annotate(value=agg).order_by(key_name)
        out = []
        for row in (annotated[:90] if key_name == 'day' else annotated[:24] if key_name == 'month' else annotated[:10]):
            k = row.get(key_name)
            name = ''
            if k:
                name = k.isoformat()[:10] if hasattr(k, 'isoformat') else str(k)
                if key_name == 'month' and hasattr(k, 'strftime'):
                    name = k.strftime('%Y-%m')
                elif key_name == 'year' and hasattr(k, 'year'):
                    name = str(k.year)
            out.append({'name': name, 'value': float(row.get('value') or 0), 'total': _decimal_str(row.get('value'))})
        return out

    # Sales report (orders)
    orders_qs = Order.objects.filter(restaurant_id__in=scope_rid).exclude(status=OrderStatus.REJECTED)
    if date_from:
        orders_qs = orders_qs.filter(created_at__date__gte=date_from)
    if date_to:
        orders_qs = orders_qs.filter(created_at__date__lte=date_to)
    sales_agg = orders_qs.annotate(**{key_name: annotate_fn}).values(key_name).annotate(value=Sum('total')).order_by(key_name)
    sales_report = []
    for row in (sales_agg[:90] if key_name == 'day' else sales_agg[:24] if key_name == 'month' else sales_agg[:10]):
        k = row.get(key_name)
        name = k.isoformat()[:10] if k and hasattr(k, 'isoformat') else (k.strftime('%Y-%m') if k and hasattr(k, 'strftime') else (str(k.year) if k and hasattr(k, 'year') else ''))
        sales_report.append({'name': name or '', 'value': float(row.get('value') or 0), 'total': _decimal_str(row.get('value'))})

    # Purchase report
    purchase_report = _series(Purchase.objects.all(), 'created_at', 'total')

    # Expense report
    expense_report = _series(Expenses.objects.all(), 'created_at', 'amount')

    # Paid / Received
    paid_agg = PaidRecord.objects.filter(restaurant_id__in=scope_rid)
    if date_from:
        paid_agg = paid_agg.filter(created_at__date__gte=date_from)
    if date_to:
        paid_agg = paid_agg.filter(created_at__date__lte=date_to)
    paid_agg = paid_agg.annotate(**{key_name: annotate_fn}).values(key_name).annotate(value=Sum('amount')).order_by(key_name)
    paid_list = []
    for row in (list(paid_agg)[:90] if key_name == 'day' else list(paid_agg)[:24] if key_name == 'month' else list(paid_agg)[:10]):
        k = row.get(key_name)
        name = k.isoformat()[:10] if k and hasattr(k, 'isoformat') else (k.strftime('%Y-%m') if k and hasattr(k, 'strftime') else (str(k.year) if k and hasattr(k, 'year') else ''))
        paid_list.append({'name': name or '', 'value': float(row.get('value') or 0), 'total': _decimal_str(row.get('value'))})

    received_agg = ReceivedRecord.objects.filter(restaurant_id__in=scope_rid)
    if date_from:
        received_agg = received_agg.filter(created_at__date__gte=date_from)
    if date_to:
        received_agg = received_agg.filter(created_at__date__lte=date_to)
    received_agg = received_agg.annotate(**{key_name: annotate_fn}).values(key_name).annotate(value=Sum('amount')).order_by(key_name)
    received_list = []
    for row in (list(received_agg)[:90] if key_name == 'day' else list(received_agg)[:24] if key_name == 'month' else list(received_agg)[:10]):
        k = row.get(key_name)
        name = k.isoformat()[:10] if k and hasattr(k, 'isoformat') else (k.strftime('%Y-%m') if k and hasattr(k, 'strftime') else (str(k.year) if k and hasattr(k, 'year') else ''))
        received_list.append({'name': name or '', 'value': float(row.get('value') or 0), 'total': _decimal_str(row.get('value'))})

    # Stock movement (list recent StockLog rows, optionally filtered by date)
    stock_qs = StockLog.objects.filter(restaurant_id__in=scope_rid).select_related('raw_material').order_by('-created_at')[:200]
    if date_from:
        stock_qs = stock_qs.filter(created_at__date__gte=date_from)
    if date_to:
        stock_qs = stock_qs.filter(created_at__date__lte=date_to)
    stock_movement = []
    for sl in stock_qs:
        stock_movement.append({
            'id': sl.id,
            'date': sl.created_at.isoformat() if sl.created_at else None,
            'type': sl.type,
            'quantity': str(sl.quantity),
            'raw_material_name': sl.raw_material.name if sl.raw_material_id else '—',
            'restaurant_id': sl.restaurant_id,
        })

    restaurants = [{'id': r.id, 'name': r.name} for r in Restaurant.objects.filter(id__in=rid).order_by('name')]

    return JsonResponse({
        'sales_report': sales_report,
        'purchase_report': purchase_report,
        'expense_report': expense_report,
        'paid_received_report': {'paid': paid_list, 'received': received_list},
        'stock_movement': stock_movement,
        'restaurants': restaurants,
        'filters': {
            'date_from': date_from.isoformat() if date_from else None,
            'date_to': date_to.isoformat() if date_to else None,
            'group_by': group_by,
            'restaurant_id': filter_rid,
        },
    })


@auth_required
@require_http_methods(['GET'])
def owner_reports_export(request):
    """GET /owner/reports/export/?format=csv|pdf|excel&date_from=&date_to=&restaurant_id=
    Export owner report data. Requires view_reports permission (enforced at URL layer).
    """
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'No restaurants'}, status=403)

    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    restaurant_id = request.GET.get('restaurant_id')
    try:
        filter_rid = int(restaurant_id) if restaurant_id else None
    except (TypeError, ValueError):
        filter_rid = None
    if filter_rid and filter_rid not in rid and not getattr(request.user, 'is_superuser', False):
        filter_rid = None
    scope_rid = [filter_rid] if filter_rid else rid

    # Reuse same queries as owner_reports for sales, purchase, expense, paid/received, stock
    orders_qs = Order.objects.filter(restaurant_id__in=scope_rid).exclude(status=OrderStatus.REJECTED)
    if date_from:
        orders_qs = orders_qs.filter(created_at__date__gte=date_from)
    if date_to:
        orders_qs = orders_qs.filter(created_at__date__lte=date_to)
    sales_total = orders_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    purchase_qs = Purchase.objects.filter(restaurant_id__in=scope_rid)
    if date_from:
        purchase_qs = purchase_qs.filter(created_at__date__gte=date_from)
    if date_to:
        purchase_qs = purchase_qs.filter(created_at__date__lte=date_to)
    purchase_total = purchase_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    expense_qs = Expenses.objects.filter(restaurant_id__in=scope_rid)
    if date_from:
        expense_qs = expense_qs.filter(created_at__date__gte=date_from)
    if date_to:
        expense_qs = expense_qs.filter(created_at__date__lte=date_to)
    expense_total = expense_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    export_format = (request.GET.get('format') or 'csv').lower()
    if export_format not in ('csv', 'pdf', 'excel'):
        export_format = 'csv'

    if export_format == 'pdf':
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.units import mm
        buf = io.BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        c.setFont('Helvetica', 14)
        c.drawString(20 * mm, 270 * mm, 'Owner Report')
        c.setFont('Helvetica', 10)
        y = 255 * mm
        if date_from or date_to:
            c.drawString(20 * mm, y, f'Period: {date_from or "start"} to {date_to or "end"}')
            y -= 6 * mm
        c.drawString(20 * mm, y, f'Sales total: {_decimal_str(sales_total)}')
        y -= 5 * mm
        c.drawString(20 * mm, y, f'Purchase total: {_decimal_str(purchase_total)}')
        y -= 5 * mm
        c.drawString(20 * mm, y, f'Expense total: {_decimal_str(expense_total)}')
        y -= 5 * mm
        c.save()
        buf.seek(0)
        resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="owner_report.pdf"'
        return resp

    if export_format == 'excel':
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = 'Report'
            ws.append(['Owner Report'])
            ws.append(['Date from', date_from.isoformat() if date_from else ''])
            ws.append(['Date to', date_to.isoformat() if date_to else ''])
            ws.append([])
            ws.append(['Metric', 'Total'])
            ws.append(['Sales', _decimal_str(sales_total)])
            ws.append(['Purchases', _decimal_str(purchase_total)])
            ws.append(['Expenses', _decimal_str(expense_total)])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            resp = HttpResponse(buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            resp['Content-Disposition'] = 'attachment; filename="owner_report.xlsx"'
            return resp
        except ImportError:
            pass  # fall back to CSV

    # CSV
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Owner Report'])
    w.writerow(['Date from', date_from.isoformat() if date_from else ''])
    w.writerow(['Date to', date_to.isoformat() if date_to else ''])
    w.writerow([])
    w.writerow(['Metric', 'Total'])
    w.writerow(['Sales', _decimal_str(sales_total)])
    w.writerow(['Purchases', _decimal_str(purchase_total)])
    w.writerow(['Expenses', _decimal_str(expense_total)])
    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="owner_report.csv"'
    return resp
