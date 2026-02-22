# b2b_site/urls.py

from django.contrib import admin
from django.urls import path
# 记得导入 get_new_order_count
from django.conf import settings
from django.conf.urls.static import static
# 确保包含了 register_view
from core.views import product_list, checkout, confirm_order, get_new_order_count, register_view

urlpatterns = [
    path('admin/', admin.site.urls),

    # === 新增：查询新订单数量的API ===
    path('api/admin/check-orders/', get_new_order_count, name='check_orders'),

    path('', product_list, name='product_list'),
    # 修改：原来的 place-order 改为两个步骤
    path('checkout/', checkout, name='checkout'),  # 第一步：预览
    path('confirm-order/', confirm_order, name='confirm'),  # 第二步：提交
    path('register/', register_view, name='register'),
]

# === 新增：在开发环境下服务媒体文件 ===
# 这段代码的意思是：如果有人访问 /media/xxx.jpg，就去 MEDIA_ROOT 目录找
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)