from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.utils.html import format_html
from django.contrib.auth.models import User
# === 关键修复：下面这一行必须有，且必须写对 ===
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
import pandas as pd
from .models import Product, ProductStock, UserProfile, IncomingStock, Order, OrderItem
# 假设您之前有 ExcelUploadForm，如果报错找不到 forms 可以暂时注释掉下面这行
from .forms import ExcelUploadForm

# 1. 定义 UserProfile 的内联样式，这样可以在用户管理界面直接改配置
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = '客户B2B配置 (地区/仓库/推荐)'

# 重新注册 User Admin
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, )

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# 2. 注册在途库存管理
@admin.register(IncomingStock)
class IncomingStockAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'qty', 'arrival_date')
    list_filter = ('warehouse', 'arrival_date')
    search_fields = ('product__sku', 'product__name')

class StockInline(admin.TabularInline):
    model = ProductStock
    extra = 0

# --- 1. 库存明细的独立管理界面 (这就是您想看到的那个表格) ---
@admin.register(ProductStock)
class StockAdmin(admin.ModelAdmin):
    # 显示产品的信息（跨表查询）和仓库信息
    list_display = ('get_sku', 'get_name', 'warehouse', 'stock_org', 'qty')
    list_filter = ('warehouse', 'stock_org')
    search_fields = ('product__sku', 'product__name', 'warehouse')

    def get_sku(self, obj):
        return obj.product.sku

    get_sku.short_description = '规格型号'

    def get_name(self, obj):
        return obj.product.name

    get_name.short_description = '物料名称'

# --- 2. 产品基础信息管理界面 ---
class StockInline(admin.TabularInline):
    model = ProductStock
    extra = 0  # 默认不显示空行

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # 在产品详情页，直接显示下面的库存列表
    inlines = [StockInline]

    # 列表显示总库存
    list_display = ('sku', 'image_tag', 'name', 'mnemonic', 'total_qty')
    search_fields = ('sku', 'name', 'mnemonic')

    # <--- 3. 新增一个方法，用来生成图片的 HTML 标签
    def image_tag(self, obj):
        if obj.image:
            # 如果有图片，返回一个高50px的图片标签
            # format_html 是为了安全地生成 HTML
            return format_html(
                '<img src="{}" style="height:50px; width:auto; border-radius:4px; border:1px solid #ddd;" />',
                obj.image.url)
        else:
            # 如果没图片，显示灰色占位符
            return format_html('<span style="color:#ccc;">{}</span>', "无图")

    # 给这个新列起个名字显示在表头
    image_tag.short_description = '图片预览'

    change_list_template = "admin/product_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('upload-excel/', self.upload_excel, name='upload_excel'), ]
        return my_urls + urls

    def upload_excel(self, request):
        if request.method == "POST":
            form = ExcelUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    self.process_excel(request.FILES['file'], form.cleaned_data['upload_type'])
                    self.message_user(request, "Excel 导入成功！")
                except Exception as e:
                    self.message_user(request, f"导入失败: {e}", level="error")
                return redirect("..")
        else:
            form = ExcelUploadForm()
        return render(request, "admin/upload_form.html", {"form": form})

    # === 核心修改：导入逻辑 ===
    def process_excel(self, file, u_type):
        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        df = df.fillna('')

        for _, row in df.iterrows():
            sku_val = str(row.get('规格型号') or row.get('物料编码') or row.get('SKU') or '').strip()
            if not sku_val: continue

            # 1. 先确保【产品基础】存在
            product, _ = Product.objects.get_or_create(sku=sku_val)

            # 更新基础信息
            if row.get('物料名称'): product.name = row.get('物料名称')
            if row.get('助记码'): product.mnemonic = row.get('助记码')

            if u_type == 'spec':
                product.price = row.get('价格') or product.price
                product.spec_details = row.get('详细规格') or product.spec_details

            elif u_type == 'procurement':
                product.incoming_qty = row.get('在途数量') or 0
                product.estimated_delivery = row.get('预计交期') or ''

            product.save()

            # 2. 如果是库存表，则更新【库存明细】
            if u_type == 'stock':
                wh_name = row.get('仓库名称') or row.get('仓库') or '默认仓库'

                # 查找或创建 (SKU + 仓库) 的组合
                stock_item, _ = ProductStock.objects.get_or_create(
                    product=product,
                    warehouse=wh_name
                )

                # 更新数量和组织
                raw_qty = row.get('可用量(主单位)') or row.get('即时库存') or 0
                try:
                    stock_item.qty = int(float(raw_qty))
                except:
                    stock_item.qty = 0

                stock_item.stock_org = row.get('库存组织') or stock_item.stock_org
                stock_item.save()

# 订单管理与导出
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'created_at', 'status')
    inlines = [OrderItemInline]
    actions = ['export_purchase_sheet']

    @admin.action(description='一键生成采购表格')
    def export_purchase_sheet(self, request, queryset):
        data = []
        for order in queryset:
            for item in order.items.all():
                data.append({
                    "客户": order.customer.username,
                    "SKU": item.product.sku,
                    "产品名称": item.product.name,
                    "需求数量": item.quantity,
                    "当前库存": item.product.qty,
                    "采购在途": item.product.incoming_qty,
                    "预计交期": item.product.estimated_delivery
                })

        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="Purchase_List.xlsx"'
        df.to_excel(response, index=False)
        return response

# 注册用户扩展
@admin.register(UserProfile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone')