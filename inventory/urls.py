from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.ProductListView.as_view(), name='product_list'),
    path('add/', views.ProductCreateView.as_view(), name='product_add'),
    path('<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('<int:pk>/qr/download/', views.download_qr, name='download_qr'),
    path('<int:pk>/sell/', views.sell_product, name='sell_product'),
    path('<int:pk>/restock/', views.restock_product, name='restock_product'),

    path('sales/', views.SalesListView.as_view(), name='sales_list'),

    path('cashiers/', views.CashierListView.as_view(), name='cashier_list'),
    path('cashiers/add/', views.CashierCreateView.as_view(), name='cashier_add'),
    path('cashiers/<int:pk>/delete/', views.CashierDeleteView.as_view(), name='cashier_delete'),

    path('settings/', views.account_settings, name='account_settings'),
    path('settings/clear-data/', views.clear_my_data, name='clear_my_data'),
    path('settings/delete-account/', views.delete_my_account, name='delete_my_account'),
    path('settings/system-reset/', views.system_reset, name='system_reset'),

    path('pos/', views.pos, name='pos'),
    path('pos/lookup/', views.pos_lookup, name='pos_lookup'),
    path('pos/complete/', views.pos_complete, name='pos_complete'),
    path('receipts/', views.receipts_list, name='receipts_list'),
    path('receipts/<int:pk>/', views.receipt_detail, name='receipt_detail'),

    path('signup/', views.signup_step1, name='signup'),
    path('signup/verify/', views.signup_verify, name='signup_verify'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
