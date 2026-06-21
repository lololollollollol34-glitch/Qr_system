from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_product_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='nickname',
            field=models.CharField(blank=True, help_text='Используется кассиром для входа, уникален в рамках одного владельца.', max_length=150, verbose_name='Логин кассира (видимый)'),
        ),
        migrations.AddConstraint(
            model_name='profile',
            constraint=models.UniqueConstraint(condition=models.Q(('role', 'cashier')), fields=('owner', 'nickname'), name='unique_cashier_nickname_per_owner'),
        ),
    ]
