"""
Business logic hooks (signals / service layer).
Implements all 13 PDF calculation points with idempotency where needed.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver

from .models import (
    Attendance,
    AttendanceStatus,
    CustomerRestaurant,
    Expenses,
    Order,
    OrderItem,
    OrderStatus,
    PaidRecord,
    PaymentStatus,
    Purchase,
    PurchaseItem,
    ReceivedRecord,
    ShareholderWithdrawal,
    Staff,
    User,
    Vendor,
    WithdrawalStatus,
)
from . import services


# Store previous status for ShareholderWithdrawal so we only deduct once when status becomes approved
_withdrawal_previous_status = {}


@receiver(pre_save, sender=ShareholderWithdrawal)
def _store_previous_withdrawal_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = ShareholderWithdrawal.objects.get(pk=instance.pk)
            _withdrawal_previous_status[instance.pk] = old.status
        except ShareholderWithdrawal.DoesNotExist:
            pass


@receiver(post_save, sender=Purchase)
def on_purchase_save(sender, instance, created, **kwargs):
    """Rule 1 & 6: Update vendor(s) to_pay from items; add stock + StockLog. Idempotent."""
    if not instance.pk:
        return
    if not created:
        return
    if instance.stock_logs.exists():
        return

    with transaction.atomic():
        # Aggregate by vendor from purchase items (raw_material.vendor)
        per_vendor = (
            PurchaseItem.objects.filter(purchase=instance)
            .values("raw_material__vendor_id")
            .annotate(total=Sum("total"))
        )
        for row in per_vendor:
            vid = row["raw_material__vendor_id"]
            if vid and row["total"]:
                Vendor.objects.filter(pk=vid).update(
                    to_pay=F("to_pay") + row["total"]
                )
        services.add_stock_for_purchase(instance)


@receiver(post_save, sender=Order)
def on_order_save(sender, instance, created, **kwargs):
    """Rule 1, 4, 6, 9: ReceivedRecord when paid; CustomerRestaurant to_receive; transaction fee to due_balance; stock when READY."""
    if not instance.pk:
        return

    with transaction.atomic():
        paid = instance.payment_status in (
            PaymentStatus.SUCCESS,
            PaymentStatus.PAID,
        )
        if not paid and created and instance.customer_id:
            cr = CustomerRestaurant.objects.filter(
                customer_id=instance.customer_id,
                restaurant_id=instance.restaurant_id,
            ).first()
            if cr and instance.total:
                CustomerRestaurant.objects.filter(pk=cr.pk).update(
                    to_pay=F("to_pay") + instance.total
                )
        if paid and not instance.received_records.exists():
            ReceivedRecord.objects.create(
                restaurant=instance.restaurant,
                name=f"Order #{instance.id}",
                customer=instance.customer,
                order=instance,
                amount=instance.total,
                payment_method=instance.payment_method or "",
            )
            # ReceivedRecord post_save will decrease CustomerRestaurant.to_pay
            fee = services.get_transaction_fee_for_order(instance.total)
            if fee and fee > 0:
                services.record_transaction_fee_to_due(instance.restaurant, fee)

        if instance.status == OrderStatus.READY:
            services.deduct_stock_for_order(instance)


@receiver(post_save, sender=Expenses)
def on_expenses_save(sender, instance, created, **kwargs):
    """Rule 1: When Expenses created with vendor, add amount to vendor.to_pay."""
    if not created or not instance.pk:
        return
    if instance.vendor_id and instance.amount:
        Vendor.objects.filter(pk=instance.vendor_id).update(
            to_pay=F("to_pay") + instance.amount
        )


@receiver(post_save, sender=Attendance)
def on_attendance_save(sender, instance, created, **kwargs):
    """Rule 2: Present or leave -> add per_day_salary to staff.to_pay."""
    if not created or not instance.pk:
        return
    if instance.status in (AttendanceStatus.PRESENT, AttendanceStatus.LEAVE):
        salary = instance.staff.per_day_salary or Decimal("0")
        if salary > 0:
            Staff.objects.filter(pk=instance.staff_id).update(
                to_pay=F("to_pay") + salary
            )


@receiver(post_save, sender=PaidRecord)
def on_paid_record_save(sender, instance, created, **kwargs):
    """Rule 3: Decrease vendor.to_pay or staff.to_pay by amount."""
    if not created or not instance.pk:
        return
    amount = instance.amount
    if amount <= 0:
        return
    with transaction.atomic():
        if instance.vendor_id:
            Vendor.objects.filter(pk=instance.vendor_id).update(
                to_pay=F("to_pay") - amount
            )
            Vendor.objects.filter(pk=instance.vendor_id, to_pay__lt=0).update(
                to_pay=0
            )
        if instance.staff_id:
            Staff.objects.filter(pk=instance.staff_id).update(
                to_pay=F("to_pay") - amount
            )
            Staff.objects.filter(pk=instance.staff_id, to_pay__lt=0).update(
                to_pay=0
            )


@receiver(post_save, sender=ReceivedRecord)
def on_received_record_save(sender, instance, created, **kwargs):
    """Rule 3: Decrease CustomerRestaurant to_pay by amount (customer paid us)."""
    if not created or not instance.pk:
        return
    if not instance.customer_id or not instance.restaurant_id:
        return
    amount = instance.amount
    if amount <= 0:
        return
    cr = CustomerRestaurant.objects.filter(
        customer_id=instance.customer_id,
        restaurant_id=instance.restaurant_id,
    ).first()
    if cr:
        CustomerRestaurant.objects.filter(pk=cr.pk).update(
            to_pay=F("to_pay") - amount
        )
        CustomerRestaurant.objects.filter(pk=cr.pk, to_pay__lt=0).update(
            to_pay=0
        )


@receiver(post_save, sender=ShareholderWithdrawal)
def on_shareholder_withdrawal_save(sender, instance, created, **kwargs):
    """Rule 11: When status becomes approved, deduct amount from user.balance. Once only."""
    if instance.status != WithdrawalStatus.APPROVED:
        return
    prev = _withdrawal_previous_status.pop(instance.pk, None)
    if prev == WithdrawalStatus.APPROVED:
        return
    amount = instance.amount
    if amount <= 0:
        return
    User.objects.filter(pk=instance.user_id).update(
        balance=F("balance") - amount
    )
    User.objects.filter(pk=instance.user_id, balance__lt=0).update(balance=0)


def _recompute_order_total(order_id):
    """Recompute order.total from sum of order items."""
    result = OrderItem.objects.filter(order_id=order_id).aggregate(s=Sum("total"))
    total = result.get("s") or Decimal("0")
    Order.objects.filter(pk=order_id).update(total=total)


@receiver(post_save, sender=OrderItem)
def on_order_item_save(sender, instance, created, **kwargs):
    """Recompute order.total when items change."""
    if instance.order_id:
        _recompute_order_total(instance.order_id)


@receiver(post_delete, sender=OrderItem)
def on_order_item_delete(sender, instance, **kwargs):
    """Recompute order.total when an item is removed."""
    if instance.order_id:
        _recompute_order_total(instance.order_id)
