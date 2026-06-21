import random
import string
from io import BytesIO

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver

def generate_product_id():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

class Profile(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_CASHIER = 'cashier'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Владелец'),
        (ROLE_CASHIER, 'Кассир'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_OWNER)
    nickname = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Логин кассира (видимый)',
        help_text='Используется кассиром для входа, уникален в рамках одного владельца.',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='cashiers',
        verbose_name='Владелец аккаунта',
    )

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'nickname'],
                condition=models.Q(role='cashier'),
                name='unique_cashier_nickname_per_owner',
            )
        ]

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'

    def get_owner(self):
        if self.role == self.ROLE_CASHIER and self.owner_id:
            return self.owner
        return self.user

class Product(models.Model):

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name='Владелец',
    )
    product_id = models.CharField(
        max_length=10,
        unique=True,
        editable=False,
        verbose_name='ID товара',
    )
    name = models.CharField(max_length=255, verbose_name='Название')
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Цена',
    )
    quantity = models.PositiveIntegerField(default=0, verbose_name='Количество')
    photo = models.ImageField(
        upload_to='product_photos/',
        blank=True,
        null=True,
        verbose_name='Фото товара',
    )
    qr_code = models.ImageField(
        upload_to='qr_codes/',
        blank=True,
        editable=False,
        verbose_name='QR-код',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self):
        return f'{self.name} ({self.product_id})'

    def _generate_unique_id(self):
        new_id = generate_product_id()
        while Product.objects.filter(product_id=new_id).exists():
            new_id = generate_product_id()
        return new_id

    def _qr_payload(self):
        if self.price is not None:
            return f'{self.product_id}|{self.name}|{self.price}'
        return f'{self.product_id}|{self.name}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if not self.product_id:
            self.product_id = self._generate_unique_id()

        if is_new or not self.qr_code:
            qr_img = qrcode.make(self._qr_payload())
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            filename = f'{self.product_id}.png'
            self.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)

        super().save(*args, **kwargs)

class Sale(models.Model):

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sales',
        verbose_name='Владелец',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='sales',
        verbose_name='Товар',
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='made_sales',
        verbose_name='Продавец',
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='Количество')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за шт.')
    total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата продажи')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Продажа'
        verbose_name_plural = 'Продажи'

    def __str__(self):
        return f'{self.product.name} x{self.quantity}'

    def save(self, *args, **kwargs):
        if self.price is None:
            self.price = self.product.price or 0
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)


class Receipt(models.Model):
    PAYMENT_CASH = 'cash'
    PAYMENT_CARD = 'card'
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Наличными'),
        (PAYMENT_CARD, 'Безналичными'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='receipts',
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='cashier_receipts',
    )
    number = models.PositiveIntegerField(verbose_name='Номер чека')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default=PAYMENT_CASH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Чек'
        verbose_name_plural = 'Чеки'

    def __str__(self):
        return f'Чек #{self.number}'

    @classmethod
    def next_number(cls, owner):
        last = cls.objects.filter(owner=owner).order_by('-number').first()
        return (last.number + 1) if last else 1


class ReceiptItem(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    product_id_str = models.CharField(max_length=10)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.total = (self.price - self.discount) * self.quantity
        super().save(*args, **kwargs)


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def delete_cashiers_with_owner(sender, instance, **kwargs):
    cashier_profiles = Profile.objects.filter(owner=instance, role=Profile.ROLE_CASHIER)
    for profile in cashier_profiles:
        profile.user.delete()


class EmailVerification(models.Model):
    email = models.EmailField()
    nickname = models.CharField(max_length=150)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        from django.utils import timezone
        return (timezone.now() - self.created_at).total_seconds() > 600

    def __str__(self):
        return f'{self.email} - {self.code}'
