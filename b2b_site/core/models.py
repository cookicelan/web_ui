from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import models
from django.db.models import Sum  # <--- 必须要有这一行，且是大写的 Sum


# 1. 修改 UserProfile：增加权限控制字段
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True, verbose_name="手机号码")

    # === 新增功能 ===
    country_suffix = models.CharField(max_length=10, blank=True, help_text="例如填 TW，系统只显示SKU中包含 -TW 的商品",
                                      verbose_name="地区后缀代码")

    # 允许可见的仓库 (用逗号分隔，例如: "深圳仓,香港仓")
    allowed_warehouses = models.CharField(max_length=500, blank=True, default="ALL",
                                          help_text="填'ALL'看全部，或填具体仓库名用逗号隔开",
                                          verbose_name="可见仓库列表")

    # 屏蔽的商品名称关键字 (用逗号分隔)
    blocked_product_keywords = models.TextField(blank=True, help_text="包含这些字的商品，该客户看不见",
                                                verbose_name="屏蔽商品名称关键字")

    # 管理员手动指定的推荐商品
    recommended_products = models.ManyToManyField('Product', blank=True, related_name='recommended_to_users',
                                                  verbose_name="专属推荐商品")

    def __str__(self):
        return f"{self.user.username} 的配置"

# 信号：创建User时自动创建UserProfile
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


# 1. 产品基础信息表 (只存不变的信息)
class Product(models.Model):
    sku = models.CharField(max_length=100, unique=True, verbose_name="规格型号(SKU)")
    name = models.CharField(max_length=200, verbose_name="物料名称")
    mnemonic = models.CharField(max_length=100, blank=True, verbose_name="助记码")

    # 规格与价格
    spec_details = models.TextField(blank=True, verbose_name="详细规格参数")
    image = models.ImageField(upload_to='products/', blank=True, verbose_name="产品图片")

    # 采购在途 (通常也不分仓库，或者您可以选择放入Stock表，这里暂且放总表)
    incoming_qty = models.IntegerField(default=0, verbose_name="采购在途数量")
    estimated_delivery = models.CharField(max_length=100, blank=True, verbose_name="预计交期")

    def __str__(self):
        return f"{self.sku} - {self.name}"

    # 这是一个“计算属性”，让前台能直接读取所有仓库的总库存
    @property
    def total_qty(self):
        # 统计该产品下所有 ProductStock 的 qty 之和
        result = self.stocks.aggregate(total=Sum('qty'))
        return result['total'] or 0

    class Meta:
        verbose_name = "产品基础信息"
        verbose_name_plural = "产品基础信息"


# 2. 新增：库存明细表 (存仓库和数量)
class ProductStock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stocks', verbose_name="所属产品")
    warehouse = models.CharField(max_length=100, verbose_name="仓库名称")
    stock_org = models.CharField(max_length=100, blank=True, verbose_name="库存组织")
    qty = models.IntegerField(default=0, verbose_name="库存数量")

    class Meta:
        # 联合唯一约束：同一个产品在同一个仓库只能有一条记录
        unique_together = ('product', 'warehouse')
        verbose_name = "库存明细"
        verbose_name_plural = "库存明细"

    def __str__(self):
        return f"{self.product.sku} - {self.warehouse}: {self.qty}"

# 3. 订单系统
class Order(models.Model):
    # 1. 修改：允许 customer 为空 (null=True)，以便游客下单
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="下单客户(账号)")

    # 2. 新增：游客信息字段
    guest_name = models.CharField(max_length=100, default="Guest", verbose_name="客户姓名")
    guest_phone = models.CharField(max_length=50, verbose_name="联系电话")
    guest_email = models.EmailField(max_length=100, blank=True, verbose_name="电子邮箱")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="下单时间")
    status = models.CharField(max_length=20, default='New', choices=[('New', '新订单'), ('Done', '已完成')])

    def __str__(self):
        # 显示姓名（如果有账号显示账号名，没账号显示填写的名字）
        name = self.customer.username if self.customer else self.guest_name
        return f"订单 #{self.id} - {name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(verbose_name="数量")

    @property
    def total_price(self):
        return self.product.price * self.quantity

# 2. 新增：在途库存表 (用于管理什么货、什么时候到、到哪个仓)
class IncomingStock(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, verbose_name="产品")
    warehouse = models.CharField(max_length=100, verbose_name="目的仓库")
    qty = models.IntegerField(default=0, verbose_name="补货数量")
    arrival_date = models.DateField(verbose_name="预计到货日期")
    note = models.CharField(max_length=200, blank=True, verbose_name="备注")

    class Meta:
        verbose_name = "在途/补货管理"
        verbose_name_plural = "在途/补货管理"