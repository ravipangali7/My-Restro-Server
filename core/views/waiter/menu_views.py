"""Waiter menu API: read-only products and categories for the waiter's restaurant."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count

from core.models import Product, Category
from core.permissions import get_waiter_restaurant
from core.views.owner.product_views import _product_to_dict
from core.views.owner.category_views import _category_to_dict


@require_http_methods(['GET'])
def waiter_product_list(request):
    """List products (menu items) for the waiter's restaurant. Same shape as owner product list."""
    restaurant = get_waiter_restaurant(request)
    if not restaurant:
        return JsonResponse({'error': 'No restaurant assigned', 'results': []}, status=403)
    category_id = request.GET.get('category_id')
    qs = Product.objects.filter(restaurant_id=restaurant.id).select_related('category').prefetch_related('variants__unit')
    if category_id:
        try:
            qs = qs.filter(category_id=int(category_id))
        except ValueError:
            pass
    results = [_product_to_dict(p, request=request) for p in qs.order_by('name')]
    total_products = len(results)
    product_ids = [p['id'] for p in results]
    products_with_discount = Product.objects.filter(
        id__in=product_ids
    ).filter(variants__discount__gt=0).distinct().count() if product_ids else 0
    stats = {
        'total_products': total_products,
        'products_with_discount': products_with_discount,
    }
    return JsonResponse({'stats': stats, 'results': results})


@require_http_methods(['GET'])
def waiter_category_list(request):
    """List categories for the waiter's restaurant. Same shape as owner category list."""
    restaurant = get_waiter_restaurant(request)
    if not restaurant:
        return JsonResponse({'error': 'No restaurant assigned', 'results': [], 'total': 0}, status=403)
    qs = Category.objects.filter(restaurant_id=restaurant.id).annotate(item_count=Count('products'))
    results = [_category_to_dict(c, item_count=c.item_count, request=request) for c in qs.order_by('name')]
    return JsonResponse({'results': results, 'total': len(results)})
