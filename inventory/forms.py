from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Product, Sale


class EmailSendForm(forms.Form):
    nickname = forms.CharField(
        label='Никнейм',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Например: Иван или ivan_shop',
            'autofocus': True,
        }),
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'you@gmail.com',
        }),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Этот email уже зарегистрирован.')
        return email


class EmailVerifyForm(forms.Form):
    code = forms.CharField(
        label='Код из письма',
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '123456',
            'autofocus': True,
            'maxlength': '6',
            'inputmode': 'numeric',
        }),
    )

class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'Пароль'
        self.fields['password2'].label = 'Повторите пароль'
        for field in ('password1', 'password2'):
            self.fields[field].widget.attrs.update({'class': 'form-control'})

    def save(self, email, nickname, commit=True):
        user = super().save(commit=False)
        user.email = email
        user.first_name = nickname
        user.username = email
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user

class CashierCreateForm(UserCreationForm):
    nickname = forms.CharField(
        label='Логин кассира',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Например: kassir1',
            'autofocus': True,
        }),
    )

    class Meta:
        model = User
        fields = []

    def __init__(self, *args, owner=None, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)
        self.fields['password1'].label = 'Пароль'
        self.fields['password2'].label = 'Повторите пароль'
        for field in ('password1', 'password2'):
            self.fields[field].widget.attrs.update({'class': 'form-control'})

    def clean_nickname(self):
        nickname = self.cleaned_data['nickname'].strip()
        if not nickname:
            raise forms.ValidationError('Укажите логин кассира.')
        if self.owner:
            from .models import Profile
            exists = Profile.objects.filter(
                owner=self.owner, role=Profile.ROLE_CASHIER, nickname=nickname
            ).exists()
            if exists:
                raise forms.ValidationError('У вас уже есть кассир с таким логином.')
        return nickname

    def save(self, commit=True):
        import uuid
        user = super().save(commit=False)
        nickname = self.cleaned_data['nickname']
        owner_id = self.owner.id if self.owner else 'x'
        user.username = f'cashier__{owner_id}__{nickname}__{uuid.uuid4().hex[:8]}'
        user.first_name = nickname
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user

class ProductForm(forms.ModelForm):

    class Meta:
        model = Product
        fields = ['name', 'price', 'quantity', 'photo']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Coca Cola 0.5л',
                'autofocus': True,
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Цена (необязательно)',
                'step': '0.01',
                'min': '0',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0',
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
        }
        labels = {
            'name': 'Название товара',
            'price': 'Цена',
            'quantity': 'Количество на складе',
            'photo': 'Фото товара (необязательно)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].required = False
        self.fields['quantity'].required = False
        self.fields['photo'].required = False

class RestockForm(forms.Form):
    amount = forms.IntegerField(
        label='Добавить на склад',
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Например: 10',
            'autofocus': True,
        }),
    )

class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label='Пароль',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autofocus': True,
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError('Неверный пароль.')
        return password


class SellForm(forms.Form):
    quantity = forms.IntegerField(
        label='Количество',
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'autofocus': True,
        }),
    )

    def __init__(self, *args, product=None, **kwargs):
        self.product = product
        super().__init__(*args, **kwargs)

    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if self.product and quantity > self.product.quantity:
            raise forms.ValidationError(
                f'На складе только {self.product.quantity} шт.'
            )
        return quantity
