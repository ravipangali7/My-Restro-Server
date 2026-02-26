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
    PaymentStatus,
    ProductRawMaterial,
    Purchase,
    PurchaseItem,
    QrStandOrder,
    RawMaterial,
    Restaurant,
    StockLog,
    StockLogType,
    SuperSetting,
    Transaction,
    TransactionCategory,
    TransactionType,
    User,
    Vendor,
)


def get_or_create_customer_for_restaurant(restaurant, phone, name=None, country_code=None):
    """
    Look up Customer by phone in this restaurant (via CustomerRestaurant).
    If country_code is provided, lookup also matches country_code (same phone, different country = different customer).
    If not found, create Customer and CustomerRestaurant with zero to_pay/to_receive.
    Returns (customer, customer_restaurant).
    """
    phone = (phone or "").strip()
    if not phone:
        return None, None

    cr_qs = CustomerRestaurant.objects.filter(
        restaurant=restaurant,
        customer__phone=phone,
    )
    if country_code is not None and country_code != "":
        cr_qs = cr_qs.filter(customer__country_code=country_code)
    cr = cr_qs.select_related("customer").first()

    if cr:
        return cr.customer, cr

    customer_qs = Customer.objects.filter(phone=phone)
    if country_code is not None and country_code != "":
        customer_qs = customer_qs.filter(country_code=country_code)
    customer = customer_qs.first()
    if not customer:
        customer = Customer.objects.create(
            name=name or phone,
            phone=phone,
            country_code=country_code or "",
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
    """Add SuperSetting whatsapp_per_usgage to restaurant.due_balance and create system Transaction for dashboard revenue."""
    ss = get_super_setting()
    if not ss.is_whatsapp_usgage or not ss.whatsapp_per_usgage:
        return
    amount = ss.whatsapp_per_usgage
    with transaction.atomic():
        Restaurant.objects.filter(pk=restaurant.pk).update(
            due_balance=F("due_balance") + amount
        )
        Transaction.objects.create(
            restaurant=None,
            amount=amount,
            transaction_type=TransactionType.IN,
            category=TransactionCategory.WHATSAPP_USAGE,
            is_system=True,
            remarks='WhatsApp usage',
        )


def record_transaction_fee_to_due(restaurant, fee_amount):
    """Add fee_amount to restaurant.due_balance and create system Transaction for dashboard revenue."""
    if not fee_amount or fee_amount <= 0:
        return
    with transaction.atomic():
        Restaurant.objects.filter(pk=restaurant.pk).update(
            due_balance=F("due_balance") + fee_amount
        )
        Transaction.objects.create(
            restaurant=None,
            amount=fee_amount,
            transaction_type=TransactionType.IN,
            category=TransactionCategory.TRANSACTION_FEE,
            is_system=True,
            remarks='Transaction fee from order',
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


# --- Owner payment services (SuperSetting logic applied) ---


def pay_subscription_fee(restaurant, amount=None):
    """
    Decrease restaurant.due_balance by amount; create Transaction (OUT, SUBSCRIPTION_FEE);
    credit SuperSetting.balance. If amount is None, use SuperSetting.subscription_fee_per_month.
    Idempotent: no-op if amount <= 0.
    """
    ss = get_super_setting()
    amt = amount if amount is not None else (ss.subscription_fee_per_month or Decimal("0"))
    amt = Decimal(str(amt)).quantize(Decimal("0.01"))
    if amt <= 0:
        return
    with transaction.atomic():
        Restaurant.objects.filter(pk=restaurant.pk).update(
            due_balance=F("due_balance") - amt
        )
        Restaurant.objects.filter(pk=restaurant.pk, due_balance__lt=0).update(due_balance=Decimal("0"))
        Transaction.objects.create(
            restaurant=restaurant,
            amount=amt,
            transaction_type=TransactionType.OUT,
            category=TransactionCategory.SUBSCRIPTION_FEE,
            payment_status=PaymentStatus.PAID,
            remarks="Subscription fee",
        )
        SuperSetting.objects.filter(pk=ss.pk).update(
            balance=F("balance") + amt
        )


def pay_qr_stand_order(qr_stand_order):
    """
    Decrease restaurant.due_balance by order total; set QrStandOrder.payment_status=PAID;
    create Transaction (OUT, QR_STAND_ORDER); credit SuperSetting.balance.
    Idempotent: skip if already paid.
    """
    if qr_stand_order.payment_status == PaymentStatus.PAID:
        return
    amt = qr_stand_order.total
    if amt <= 0:
        return
    ss = get_super_setting()
    restaurant = qr_stand_order.restaurant
    with transaction.atomic():
        Restaurant.objects.filter(pk=restaurant.pk).update(
            due_balance=F("due_balance") - amt
        )
        Restaurant.objects.filter(pk=restaurant.pk, due_balance__lt=0).update(due_balance=Decimal("0"))
        QrStandOrder.objects.filter(pk=qr_stand_order.pk).update(
            payment_status=PaymentStatus.PAID
        )
        Transaction.objects.create(
            restaurant=restaurant,
            amount=amt,
            transaction_type=TransactionType.OUT,
            category=TransactionCategory.QR_STAND_ORDER,
            payment_status=PaymentStatus.PAID,
            remarks=f"QR Stand Order #{qr_stand_order.id}",
        )
        SuperSetting.objects.filter(pk=ss.pk).update(
            balance=F("balance") + amt
        )


def pay_due_balance(restaurant, amount):
    """
    Decrease restaurant.due_balance by amount (capped at current due_balance);
    create Transaction (OUT, DUE_PAID); credit SuperSetting.balance.
    """
    amt = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amt <= 0:
        return
    restaurant.refresh_from_db()
    current_due = restaurant.due_balance or Decimal("0")
    pay_amt = min(amt, current_due)
    if pay_amt <= 0:
        return
    ss = get_super_setting()
    with transaction.atomic():
        Restaurant.objects.filter(pk=restaurant.pk).update(
            due_balance=F("due_balance") - pay_amt
        )
        Restaurant.objects.filter(pk=restaurant.pk, due_balance__lt=0).update(due_balance=Decimal("0"))
        Transaction.objects.create(
            restaurant=restaurant,
            amount=pay_amt,
            transaction_type=TransactionType.OUT,
            category=TransactionCategory.DUE_PAID,
            payment_status=PaymentStatus.PAID,
            remarks="Due balance paid",
        )
        SuperSetting.objects.filter(pk=ss.pk).update(
            balance=F("balance") + pay_amt
        )
