# b2b_site/urls.py

from django.contrib import admin
from django.urls import path
# 记得导入 get_new_order_count
from django.conf import settings
from django.conf.urls.static import static
# 找到这一行，并在末尾加上 custom_logout
from core.views import product_list, checkout, confirm_order, get_new_order_count, register_view, custom_logout, user_login_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/admin/check-orders/', get_new_order_count, name='check_orders'),

    path('', product_list, name='product_list'),
    path('checkout/', checkout, name='checkout'),
    path('confirm-order/', confirm_order, name='confirm'),
    path('register/', register_view, name='register'),

    # === 新增这行：退出登录的路由 ===
    path('logout/', custom_logout, name='logout'),
    # === 新增：客户登录路由 ===
    path('login/', user_login_view, name='user_login'),
]

# === 新增：在开发环境下服务媒体文件 ===
# 这段代码的意思是：如果有人访问 /media/xxx.jpg，就去 MEDIA_ROOT 目录找
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)