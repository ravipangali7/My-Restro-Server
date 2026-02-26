"""Super Admin reports: revenue sources, WhatsApp usage, transaction charges, system earnings; per-restaurant reports; export."""
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from datetime import timedelta, datetime
from django.utils import timezone
import csv
import io

from core.models import Transaction, SuperSetting, TransactionCategory, User, Restaurant, Order, OrderStatus


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


@require_http_methods(['GET'])
def super_admin_reports(request):
    """GET reports: revenue_sources, whatsapp_revenue, transaction_charges, system_earnings_overview. Optional: date_from, date_to, group_by=day|month|year, restaurant_id."""
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    group_by = (request.GET.get('group_by') or 'day').lower()
    if group_by not in ('day', 'month', 'year'):
        group_by = 'day'
    restaurant_id = request.GET.get('restaurant_id')
    try:
        rid = int(restaurant_id) if restaurant_id else None
    except (TypeError, ValueError):
        rid = None

    system_tx = Transaction.objects.filter(is_system=True, transaction_type='in')
    if date_from:
        system_tx = system_tx.filter(created_at__date__gte=date_from)
    if date_to:
        system_tx = system_tx.filter(created_at__date__lte=date_to)
    # Revenue by category (all time for overview; can add time filter later)
    by_category = (
        system_tx.values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    revenue_sources = [
        {'category': row['category'] or 'other', 'total': _decimal_str(row['total']), 'value': float(row['total'] or 0)}
        for row in by_category
    ]
    whatsapp_revenue = system_tx.filter(category=TransactionCategory.WHATSAPP_USAGE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    transaction_charges = system_tx.filter(category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    qr_stand = system_tx.filter(category=TransactionCategory.QR_STAND_ORDER).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    subscription = system_tx.filter(category=TransactionCategory.SUBSCRIPTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_system = system_tx.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    share_withdrawal_total = Transaction.objects.filter(category=TransactionCategory.SHARE_WITHDRAWAL).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    shareholder_balance_agg = User.objects.filter(is_shareholder=True).aggregate(s=Sum('balance'))['s'] or Decimal('0')
    setting = SuperSetting.objects.first()
    system_balance = setting.balance if setting else Decimal('0')
    system_earnings_overview = {
        'total_system_revenue': _decimal_str(total_system),
        'system_balance': _decimal_str(system_balance),
        'whatsapp_revenue': _decimal_str(whatsapp_revenue),
        'transaction_charges': _decimal_str(transaction_charges),
        'qr_stand_order_revenue': _decimal_str(qr_stand),
        'subscription_revenue': _decimal_str(subscription),
        'shareholder_total_balance': _decimal_str(shareholder_balance_agg),
        'share_withdrawal_total': _decimal_str(share_withdrawal_total),
    }
    # Time series for charts (group_by: day, month, year)
    if group_by == 'month':
        annotate_fn = TruncMonth('created_at')
        key_name = 'month'
    elif group_by == 'year':
        annotate_fn = TruncYear('created_at')
        key_name = 'year'
    else:
        annotate_fn = TruncDate('created_at')
        key_name = 'day'
    rev_qs = system_tx.annotate(**{key_name: annotate_fn}).values(key_name).annotate(value=Sum('amount')).order_by(key_name)
    if key_name == 'day':
        rev_qs = rev_qs[:90]
    elif key_name == 'month':
        rev_qs = rev_qs[:24]
    else:
        rev_qs = rev_qs[:10]
    revenue_line = []
    for row in rev_qs:
        k = row.get(key_name)
        if k:
            name = k.isoformat()[:10] if hasattr(k, 'isoformat') else str(k)
            if key_name == 'month' and hasattr(k, 'strftime'):
                name = k.strftime('%Y-%m')
            elif key_name == 'year' and hasattr(k, 'year'):
                name = str(k.year)
        else:
            name = ''
        revenue_line.append({'name': name, 'value': float(row.get('value') or 0)})

    data = {
        'revenue_sources': revenue_sources,
        'whatsapp_revenue': _decimal_str(whatsapp_revenue),
        'transaction_charges': _decimal_str(transaction_charges),
        'system_earnings_overview': system_earnings_overview,
        'revenue_line': revenue_line,
        'shareholder_total_balance': _decimal_str(shareholder_balance_agg),
        'share_withdrawal_total': _decimal_str(share_withdrawal_total),
        'filters': {'date_from': date_from.isoformat() if date_from else None, 'date_to': date_to.isoformat() if date_to else None, 'group_by': group_by, 'restaurant_id': rid},
    }
    if rid:
        rest = Restaurant.objects.filter(pk=rid).first()
        if rest:
            rest_rev = Order.objects.filter(restaurant=rest).exclude(status=OrderStatus.REJECTED)
            if date_from:
                rest_rev = rest_rev.filter(created_at__date__gte=date_from)
            if date_to:
                rest_rev = rest_rev.filter(created_at__date__lte=date_to)
            rest_total = rest_rev.aggregate(s=Sum('total'))['s'] or Decimal('0')
            data['restaurant_filter'] = {'id': rest.id, 'name': rest.name, 'revenue': _decimal_str(rest_total), 'order_count': rest_rev.count()}
    return JsonResponse(data)


@require_http_methods(['GET'])
def super_admin_reports_restaurants(request):
    """GET: list of restaurants with summary stats; or ?restaurant_id=<id> for one restaurant's report (revenue line, summary)."""
    restaurant_id = request.GET.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid restaurant_id'}, status=400)
        restaurant = Restaurant.objects.filter(pk=rid).first()
        if not restaurant:
            return JsonResponse({'error': 'Restaurant not found'}, status=404)
        # Last 30 days daily revenue for this restaurant
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        daily = (
            Order.objects.filter(restaurant=restaurant)
            .exclude(status=OrderStatus.REJECTED)
            .filter(created_at__gte=start_date, created_at__lte=end_date)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(value=Sum('total'))
            .order_by('day')
        )
        revenue_line = [
            {'name': row['day'].isoformat() if row.get('day') else '', 'value': float(row.get('value') or 0)}
            for row in daily
        ]
        total_revenue = Order.objects.filter(restaurant=restaurant).exclude(status=OrderStatus.REJECTED).aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = Order.objects.filter(restaurant=restaurant).count()
        return JsonResponse({
            'restaurant': {
                'id': restaurant.id,
                'name': restaurant.name,
                'revenue': _decimal_str(total_revenue),
                'order_count': order_count,
                'due_balance': _decimal_str(restaurant.due_balance),
            },
            'revenue_line': revenue_line,
        })
    # List all restaurants with summary
    restaurants = Restaurant.objects.all().order_by('name')
    results = []
    for r in restaurants:
        rev = Order.objects.filter(restaurant=r).exclude(status=OrderStatus.REJECTED).aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = Order.objects.filter(restaurant=r).count()
        results.append({
            'id': r.id,
            'name': r.name,
            'revenue': _decimal_str(rev),
            'order_count': order_count,
            'due_balance': _decimal_str(r.due_balance),
        })
    return JsonResponse({'restaurants': results})


@require_http_methods(['GET'])
def super_admin_reports_export(request):
    """GET reports/export/?format=csv|pdf&date_from=&date_to= - export report data as CSV or PDF."""
    export_format = (request.GET.get('format') or 'csv').lower()
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))

    system_tx = Transaction.objects.filter(is_system=True, transaction_type='in')
    if date_from:
        system_tx = system_tx.filter(created_at__date__gte=date_from)
    if date_to:
        system_tx = system_tx.filter(created_at__date__lte=date_to)

    by_category = system_tx.values('category').annotate(total=Sum('amount')).order_by('-total')
    restaurants = Restaurant.objects.all().order_by('name')
    rest_rows = []
    for r in restaurants:
        rev = Order.objects.filter(restaurant=r).exclude(status=OrderStatus.REJECTED)
        if date_from:
            rev = rev.filter(created_at__date__gte=date_from)
        if date_to:
            rev = rev.filter(created_at__date__lte=date_to)
        rest_rows.append({
            'id': r.id,
            'name': r.name,
            'revenue': rev.aggregate(s=Sum('total'))['s'] or Decimal('0'),
            'order_count': rev.count(),
            'due_balance': r.due_balance or Decimal('0'),
        })

    if export_format == 'pdf':
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.units import mm

        buf = io.BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        c.setFont('Helvetica', 14)
        c.drawString(20 * mm, 270 * mm, 'Super Admin Report')
        c.setFont('Helvetica', 10)
        y = 255 * mm
        if date_from or date_to:
            c.drawString(20 * mm, y, f'Period: {date_from or "start"} to {date_to or "end"}')
            y -= 6 * mm
        c.drawString(20 * mm, y, 'Revenue by category:')
        y -= 5 * mm
        for row in by_category[:15]:
            c.drawString(25 * mm, y, f"{row['category'] or 'other'}: {_decimal_str(row['total'])}")
            y -= 5 * mm
        y -= 5 * mm
        c.drawString(20 * mm, y, 'Restaurants summary:')
        y -= 5 * mm
        for row in rest_rows[:20]:
            c.drawString(25 * mm, y, f"{row['name']}: revenue {row['revenue']}, orders {row['order_count']}, due {row['due_balance']}")
            y -= 5 * mm
            if y < 30 * mm:
                c.showPage()
                c.setFont('Helvetica', 10)
                y = 270 * mm
        c.save()
        buf.seek(0)
        resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="super_admin_report.pdf"'
        return resp

    # CSV
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Report', 'Super Admin'])
    w.writerow(['Date from', date_from or ''])
    w.writerow(['Date to', date_to or ''])
    w.writerow([])
    w.writerow(['Category', 'Total revenue'])
    for row in by_category:
        w.writerow([row['category'] or 'other', _decimal_str(row['total'])])
    w.writerow([])
    w.writerow(['Restaurant', 'Revenue', 'Order count', 'Due balance'])
    for row in rest_rows:
        w.writerow([row['name'], _decimal_str(row['revenue']), row['order_count'], _decimal_str(row['due_balance'])])
    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="super_admin_report.csv"'
    return resp
