"""
Reusable business logic for orders, purchases, stock, fees, and share distribution.
Used by signals and views so calculations stay consistent.
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import F

from .models import (
    Customer,
    CustomerRestaurant,
    Order,
    OrderItem,
    OrderStatus,
    ProductRawMaterial,
    Purchase,
    PurchaseItem,
    RawMaterial,
    Restaurant,
    StockLog,
    StockLogType,
    SuperSetting,
    User,
    Vendor,
)


def get_or_create_customer_for_restaurant(restaurant, phone, name=None):
    """
    Look up Customer by phone in this restaurant (via CustomerRestaurant).
    If not found, create Customer and CustomerRestaurant with zero to_pay/to_receive.
    Returns (customer, customer_restaurant).
    """
    phone = (phone or "").strip()
    if not phone:
        return None, None

    cr = CustomerRestaurant.objects.filter(
        restaurant=restaurant,
        customer__phone=phone,
    ).select_related("customer").first()

    if cr:
        return cr.customer, cr

    customer = Customer.objects.filter(phone=phone).first()
    if not customer:
        customer = Customer.objects.create(
            name=name or phone,
            phone=phone,
        )
    cr, _ = CustomerRestaurant.objects.get_or_create(
        customer=customer,
        restaurant=restaurant,
        defaults={"to_pay": Decimal("0"), "to_receive": Decimal("0")},
    )
    return customer, cr


def get_super_setting():
    """Return the active SuperSetting (first row). Creates one with defaults if none exists."""
    ss = SuperSetting.objects.first()
    if ss is None:
        ss = SuperSetting.objects.create()
    return ss


def get_transaction_fee_for_order(order_total):
    """
    From SuperSetting, return per_transaction_fee (e.g. 10).
    Used to compute customer pay total and restaurant due_balance.
    """
    ss = get_super_setting()
    fee = ss.per_transaction_fee or Decimal("0")
    return fee


def add_stock_for_purchase(purchase):
    """
    For each PurchaseItem: increase raw_material.stock by quantity,
    create StockLog(type=in). Idempotent: skip if purchase already has any StockLog.
    """
    if not purchase.pk:
        return
    if StockLog.objects.filter(purchase=purchase).exists():
        return

    with transaction.atomic():
        for item in purchase.items.select_related("raw_material").all():
            rm = item.raw_material
            qty = item.quantity
            RawMaterial.objects.filter(pk=rm.pk).update(
                stock=F("stock") + qty
            )
            StockLog.objects.create(
                restaurant=purchase.restaurant,
                raw_material=rm,
                type=StockLogType.IN,
                quantity=qty,
                purchase=purchase,
                purchase_item=item,
            )


def deduct_stock_for_order(order):
    """
    When order.status == READY: for each OrderItem with product_variant,
    use ProductRawMaterial to compute consumption and decrease raw_material.stock.
    For combo_set items: use combo's products' ProductRawMaterial.
    Idempotent: skip if order already has StockLogs for this order.
    """
    if order.status != OrderStatus.READY:
        return
    if not order.pk:
        return
    if StockLog.objects.filter(order=order).exists():
        return

    with transaction.atomic():
        for item in order.items.select_related(
            "product", "product_variant", "combo_set"
        ).all():
            if item.product_variant_id:
                # Product + ProductVariant: get ProductRawMaterial rows
                links = ProductRawMaterial.objects.filter(
                    product=item.product,
                    product_variant=item.product_variant,
                ).select_related("raw_material")
                for link in links:
                    consumption = link.raw_material_quantity * item.quantity
                    RawMaterial.objects.filter(pk=link.raw_material_id).update(
                        stock=F("stock") - consumption
                    )
                    StockLog.objects.create(
                        restaurant=order.restaurant,
                        raw_material=link.raw_material,
                        type=StockLogType.OUT,
                        quantity=consumption,
                        order=order,
                        order_item=item,
                    )
            elif item.combo_set_id:
                # Combo: use each product in combo's ProductRawMaterial (with product_variant if any)
                for product in item.combo_set.products.all():
                    links = ProductRawMaterial.objects.filter(
                        product=product
                    ).select_related("raw_material")
                    for link in links:
                        consumption = link.raw_material_quantity * item.quantity
                        RawMaterial.objects.filter(
                            pk=link.raw_material_id
                        ).update(stock=F("stock") - consumption)
                        StockLog.objects.create(
                            restaurant=order.restaurant,
                            raw_material=link.raw_material,
                            type=StockLogType.OUT,
                            quantity=consumption,
                            order=order,
                            order_item=item,
                        )


def record_whatsapp_usage(restaurant):
    """Add SuperSetting whatsapp_per_usgage to restaurant.due_balance. Call from views when sending WhatsApp."""
    ss = get_super_setting()
    if not ss.is_whatsapp_usgage or not ss.whatsapp_per_usgage:
        return
    amount = ss.whatsapp_per_usgage
    Restaurant.objects.filter(pk=restaurant.pk).update(
        due_balance=F("due_balance") + amount
    )


def record_transaction_fee_to_due(restaurant, fee_amount):
    """Add fee_amount to restaurant.due_balance. Called when order is created and payment is success/paid."""
    if not fee_amount or fee_amount <= 0:
        return
    Restaurant.objects.filter(pk=restaurant.pk).update(
        due_balance=F("due_balance") + fee_amount
    )


def apply_share_distribution():
    """
    Get SuperSetting balance; get all Users with is_shareholder=True and share_percentage;
    credit each user's balance by (balance * share_percentage / 100);
    then deduct total distributed from SuperSetting.balance.
    Trigger via admin action or management command.
    """
    ss = get_super_setting()
    available = ss.balance
    if available <= 0:
        return

    shareholders = list(
        User.objects.filter(
            is_shareholder=True,
            share_percentage__isnull=False,
        ).exclude(share_percentage=0)
    )
    if not shareholders:
        return

    total_percentage = sum(
        (u.share_percentage or Decimal("0")) for u in shareholders
    )
    if total_percentage <= 0:
        return

    with transaction.atomic():
        total_distributed = Decimal("0")
        for user in shareholders:
            pct = user.share_percentage or Decimal("0")
            if pct <= 0:
                continue
            amount = (available * pct / Decimal("100")).quantize(
                Decimal("0.01")
            )
            if amount <= 0:
                continue
            User.objects.filter(pk=user.pk).update(
                balance=F("balance") + amount
            )
            total_distributed += amount

        if total_distributed > 0:
            new_balance = ss.balance - total_distributed
            SuperSetting.objects.filter(pk=ss.pk).update(
                balance=max(Decimal("0"), new_balance)
            )
