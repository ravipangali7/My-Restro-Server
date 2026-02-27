"""
Management command: set is_restaurant=False for restaurants where subscription_end < today.
Run daily via cron for automatic expiration. Safe to run multiple times.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Restaurant


class Command(BaseCommand):
    help = 'Set is_restaurant=False for restaurants with subscription_end < today'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only print what would be updated, do not save',
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        qs = Restaurant.objects.filter(
            subscription_end__lt=today,
            is_restaurant=True,
        )
        count = qs.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No restaurants to expire.'))
            return
        if options['dry_run']:
            for r in qs:
                self.stdout.write(f'Would expire: id={r.id} name={r.name} subscription_end={r.subscription_end}')
            self.stdout.write(self.style.WARNING(f'Dry run: would set is_restaurant=False for {count} restaurant(s).'))
            return
        updated = qs.update(is_restaurant=False)
        self.stdout.write(self.style.SUCCESS(f'Set is_restaurant=False for {updated} restaurant(s).'))
