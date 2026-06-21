from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, DeleteView

from .forms import CashierCreateForm, DeleteAccountForm, EmailSendForm, EmailVerifyForm, ProductForm, RestockForm, SellForm, SignUpForm
from .models import EmailVerification, Product, Profile, Sale

def get_user_owner(user):
    profile, _ = Profile.objects.get_or_create(
        user=user, defaults={'role': Profile.ROLE_OWNER}
    )
    return profile.get_owner()

class OwnerRequiredMixin(LoginRequiredMixin):

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        profile, _ = Profile.objects.get_or_create(
            user=request.user, defaults={'role': Profile.ROLE_OWNER}
        )
        if profile.role != Profile.ROLE_OWNER:
            messages.error(request, 'Этот раздел доступен только владельцу аккаунта.')
            return redirect('product_list')
        return super().dispatch(request, *args, **kwargs)

def signup_step1(request):
    import random
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    if request.method == 'POST':
        form = EmailSendForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            nickname = form.cleaned_data['nickname']
            code = str(random.randint(100000, 999999))
            EmailVerification.objects.filter(email=email).delete()
            EmailVerification.objects.create(email=email, nickname=nickname, code=code)
            try:
                send_mail(
                    subject='Код подтверждения — QR Маркет',
                    message=f'Ваш код подтверждения: {code}\n\nКод действует 10 минут.',
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception:
                messages.error(request, 'Не удалось отправить письмо. Проверьте настройки EMAIL в settings.py.')
                return render(request, 'registration/signup.html', {'form': form})
            request.session['verify_email'] = email
            return redirect('signup_verify')
    else:
        form = EmailSendForm()
    return render(request, 'registration/signup.html', {'form': form})


def signup_verify(request):
    email = request.session.get('verify_email')
    if not email:
        return redirect('signup')
    verification = EmailVerification.objects.filter(email=email, is_used=False).order_by('-created_at').first()
    if not verification:
        messages.error(request, 'Код не найден. Попробуйте снова.')
        return redirect('signup')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        code_input = request.POST.get('code', '').strip()

        if verification.is_expired():
            messages.error(request, 'Код истёк. Зарегистрируйтесь заново.')
            return redirect('signup')

        if code_input != verification.code:
            messages.error(request, 'Неверный код.')
            return render(request, 'registration/signup_verify.html', {
                'form': form, 'email': email, 'code_form': EmailVerifyForm(request.POST)
            })

        if form.is_valid():
            user = form.save(email=email, nickname=verification.nickname)
            verification.is_used = True
            verification.save()
            Profile.objects.create(user=user, role=Profile.ROLE_OWNER)
            del request.session['verify_email']
            login(request, user, backend='inventory.backends.EmailBackend')
            messages.success(request, 'Регистрация прошла успешно!')
            return redirect('product_list')
    else:
        form = SignUpForm()

    return render(request, 'registration/signup_verify.html', {
        'form': form, 'email': email, 'code_form': EmailVerifyForm()
    })

class ProductListView(LoginRequiredMixin, ListView):

    model = Product
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'

    def get_queryset(self):
        owner = get_user_owner(self.request.user)
        return Product.objects.filter(owner=owner)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _ = Profile.objects.get_or_create(
            user=self.request.user, defaults={'role': Profile.ROLE_OWNER}
        )
        context['is_owner'] = profile.role == Profile.ROLE_OWNER
        context['total_stock'] = sum(p.quantity for p in context['products'])
        return context

class ProductCreateView(OwnerRequiredMixin, CreateView):

    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('product_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        form.instance.owner = get_user_owner(self.request.user)
        return super().form_valid(form)

class ProductDeleteView(OwnerRequiredMixin, DeleteView):

    model = Product
    template_name = 'inventory/product_confirm_delete.html'
    success_url = reverse_lazy('product_list')

    def get_queryset(self):
        owner = get_user_owner(self.request.user)
        return Product.objects.filter(owner=owner)

    def form_valid(self, form):
        product = self.get_object()
        if product.qr_code:
            product.qr_code.delete(save=False)
        return super().form_valid(form)

@login_required
def download_qr(request, pk):
    owner = get_user_owner(request.user)
    product = get_object_or_404(Product, pk=pk, owner=owner)
    if not product.qr_code:
        raise Http404('QR-код не найден')
    return FileResponse(
        product.qr_code.open('rb'),
        as_attachment=True,
        filename=f'qr_{product.product_id}.png',
    )

@login_required
def sell_product(request, pk):
    owner = get_user_owner(request.user)
    product = get_object_or_404(Product, pk=pk, owner=owner)

    form = SellForm(request.POST or None, product=product)
    if request.method == 'POST' and form.is_valid():
        quantity = form.cleaned_data['quantity']
        Sale.objects.create(
            owner=owner,
            product=product,
            seller=request.user,
            quantity=quantity,
            price=product.price or 0,
        )
        product.quantity -= quantity
        product.save(update_fields=['quantity'])
        messages.success(request, f'Продано: {product.name} — {quantity} шт.')
        return redirect('product_list')

    return render(request, 'inventory/sell_product.html', {
        'product': product,
        'form': form,
    })

@login_required
def restock_product(request, pk):
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={'role': Profile.ROLE_OWNER}
    )
    if profile.role != Profile.ROLE_OWNER:
        messages.error(request, 'Пополнение склада доступно только владельцу аккаунта.')
        return redirect('product_list')

    owner = get_user_owner(request.user)
    product = get_object_or_404(Product, pk=pk, owner=owner)

    form = RestockForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        amount = form.cleaned_data['amount']
        product.quantity += amount
        product.save(update_fields=['quantity'])
        messages.success(request, f'Склад пополнен: {product.name} +{amount} шт.')
        return redirect('product_list')

    return render(request, 'inventory/restock_product.html', {
        'product': product,
        'form': form,
    })

class SalesListView(LoginRequiredMixin, ListView):

    model = Sale
    template_name = 'inventory/sales_list.html'
    context_object_name = 'sales'
    paginate_by = 50

    def get_queryset(self):
        owner = get_user_owner(self.request.user)
        return Sale.objects.filter(owner=owner).select_related('product', 'seller')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sales = self.get_queryset()
        context['total_sum'] = sum(sale.total for sale in sales)
        return context

class CashierListView(OwnerRequiredMixin, ListView):

    model = Profile
    template_name = 'inventory/cashier_list.html'
    context_object_name = 'cashiers'

    def get_queryset(self):
        return Profile.objects.filter(
            role=Profile.ROLE_CASHIER, owner=self.request.user
        ).select_related('user')

class CashierCreateView(OwnerRequiredMixin, CreateView):

    form_class = CashierCreateForm
    template_name = 'inventory/cashier_form.html'
    success_url = reverse_lazy('cashier_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        Profile.objects.create(
            user=self.object,
            role=Profile.ROLE_CASHIER,
            owner=self.request.user,
            nickname=form.cleaned_data['nickname'],
        )
        messages.success(self.request, f'Кассир «{form.cleaned_data["nickname"]}» создан.')
        return response

class CashierDeleteView(OwnerRequiredMixin, DeleteView):

    template_name = 'inventory/cashier_confirm_delete.html'
    success_url = reverse_lazy('cashier_list')
    context_object_name = 'cashier'

    def get_queryset(self):
        return Profile.objects.filter(
            role=Profile.ROLE_CASHIER, owner=self.request.user
        )

    def form_valid(self, form):
        profile = self.get_object()
        user = profile.user
        response = super().form_valid(form)
        user.delete()
        return response

@login_required
def account_settings(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={'role': Profile.ROLE_OWNER}
    )
    if profile.role != Profile.ROLE_OWNER:
        messages.error(request, 'Этот раздел доступен только владельцу аккаунта.')
        return redirect('product_list')

    return render(request, 'inventory/settings.html')

@login_required
def clear_my_data(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={'role': Profile.ROLE_OWNER}
    )
    if profile.role != Profile.ROLE_OWNER:
        messages.error(request, 'Этот раздел доступен только владельцу аккаунта.')
        return redirect('product_list')

    if request.method == 'POST':
        from .models import Receipt, ReceiptItem

        products = Product.objects.filter(owner=request.user)
        for product in products:
            if product.qr_code:
                product.qr_code.delete(save=False)
            if product.photo:
                product.photo.delete(save=False)

        ReceiptItem.objects.filter(receipt__owner=request.user).delete()
        Receipt.objects.filter(owner=request.user).delete()
        Sale.objects.filter(owner=request.user).delete()
        products.delete()
        messages.success(request, 'Все ваши товары, продажи и чеки удалены.')
        return redirect('product_list')

    return render(request, 'inventory/clear_data_confirm.html')

@login_required
def delete_my_account(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={'role': Profile.ROLE_OWNER}
    )
    if profile.role != Profile.ROLE_OWNER:
        messages.error(request, 'Этот раздел доступен только владельцу аккаунта.')
        return redirect('product_list')

    if request.method == 'POST':
        form = DeleteAccountForm(request.POST, user=request.user)
        if form.is_valid():
            for product in Product.objects.filter(owner=request.user):
                if product.qr_code:
                    product.qr_code.delete(save=False)
                if product.photo:
                    product.photo.delete(save=False)
            user = request.user
            logout(request)
            user.delete()
            messages.success(request, 'Ваш аккаунт и все данные удалены.')
            return redirect('login')
    else:
        form = DeleteAccountForm(user=request.user)

    return render(request, 'inventory/delete_account_confirm.html', {'form': form})

@login_required
def system_reset(request):
    if not request.user.is_superuser:
        messages.error(request, 'Этот раздел доступен только суперпользователю.')
        return redirect('product_list')

    if request.method == 'POST':
        form = DeleteAccountForm(request.POST, user=request.user)
        if form.is_valid():
            from .models import Receipt, ReceiptItem

            for product in Product.objects.all():
                if product.qr_code:
                    product.qr_code.delete(save=False)
                if product.photo:
                    product.photo.delete(save=False)

            ReceiptItem.objects.all().delete()
            Receipt.objects.all().delete()
            Sale.objects.all().delete()
            Product.objects.all().delete()
            Profile.objects.exclude(user=request.user).delete()
            User.objects.exclude(pk=request.user.pk).delete()

            messages.success(request, 'Система полностью очищена. Остался только ваш суперпользователь.')
            return redirect('product_list')
    else:
        form = DeleteAccountForm(user=request.user)

    return render(request, 'inventory/system_reset_confirm.html', {'form': form})


import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Receipt, ReceiptItem


@login_required
def pos(request):
    owner = get_user_owner(request.user)
    products = Product.objects.filter(owner=owner, quantity__gt=0).values(
        'id', 'product_id', 'name', 'price', 'quantity'
    )
    next_num = Receipt.next_number(owner)
    return render(request, 'inventory/pos.html', {
        'products_json': json.dumps(list(products), default=str),
        'next_number': next_num,
    })


@login_required
def pos_lookup(request):
    code = request.GET.get('code', '').strip().upper()
    owner = get_user_owner(request.user)
    try:
        product = Product.objects.get(product_id=code, owner=owner)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Товар не найден'}, status=404)
    if product.quantity <= 0:
        return JsonResponse({'error': 'Нет в наличии'}, status=400)
    return JsonResponse({
        'id': product.id,
        'product_id': product.product_id,
        'name': product.name,
        'price': str(product.price or '0'),
        'quantity': product.quantity,
    })


@login_required
@require_POST
def pos_complete(request):
    owner = get_user_owner(request.user)
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        paid = Decimal(str(data.get('paid', 0)))
        payment = data.get('payment', 'cash')
        global_discount = Decimal(str(data.get('discount', 0)))

        if not items:
            return JsonResponse({'error': 'Чек пустой'}, status=400)

        total = Decimal('0')
        receipt_items = []

        for item in items:
            product = Product.objects.get(id=item['id'], owner=owner)
            qty = int(item['quantity'])
            price = Decimal(str(item['price']))
            disc = Decimal(str(item.get('discount', 0)))

            if qty > product.quantity:
                return JsonResponse(
                    {'error': f'Недостаточно товара «{product.name}» (осталось {product.quantity} шт.)'},
                    status=400
                )

            line_total = (price - disc) * qty
            total += line_total
            receipt_items.append((product, qty, price, disc, line_total))

        total_after_discount = total - global_discount
        change = max(paid - total_after_discount, Decimal('0'))

        receipt = Receipt.objects.create(
            owner=owner,
            cashier=request.user,
            number=Receipt.next_number(owner),
            total=total_after_discount,
            discount=global_discount,
            paid=paid,
            change=change,
            payment=payment,
        )

        for product, qty, price, disc, line_total in receipt_items:
            ReceiptItem.objects.create(
                receipt=receipt,
                product=product,
                name=product.name,
                product_id_str=product.product_id,
                quantity=qty,
                price=price,
                discount=disc,
                total=line_total,
            )
            product.quantity -= qty
            product.save(update_fields=['quantity'])

        return JsonResponse({
            'ok': True,
            'receipt_number': receipt.number,
            'total': str(total_after_discount),
            'change': str(change),
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def receipts_list(request):
    owner = get_user_owner(request.user)
    receipts = Receipt.objects.filter(owner=owner).prefetch_related('items')
    total_revenue = sum(r.total for r in receipts)
    return render(request, 'inventory/receipts_list.html', {
        'receipts': receipts,
        'total_revenue': total_revenue,
    })


@login_required
def receipt_detail(request, pk):
    owner = get_user_owner(request.user)
    receipt = get_object_or_404(Receipt, pk=pk, owner=owner)
    return render(request, 'inventory/receipt_detail.html', {'receipt': receipt})

