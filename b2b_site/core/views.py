from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required # <--- 小铃铛权限需要
from django.http import JsonResponse          # <--- 【关键】缺的就是这一行，修复报错
from django.core.mail import send_mail        # <--- 发邮件需要
from django.conf import settings              # <--- 读取邮箱配置需要
from django.contrib.auth import login, logout, authenticate  # <--- 加上 authenticate
from .models import Product, Order, OrderItem, UserProfile, IncomingStock, ProductStock


# 1. 注册功能
def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')  # 用作登录账号
        password = request.POST.get('password')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        country = request.POST.get('country')  # 这里我们简单存入 country_suffix

        # 创建用户
        if User.objects.filter(username=username).exists():
            return render(request, 'user/register.html', {'error': '用户名已存在'})

        user = User.objects.create_user(username=username, email=email, password=password)

        # 创建/更新 Profile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone = phone
        profile.country_suffix = country  # 简单处理：把输入的地区直接当后缀存
        profile.save()

        login(request, user)
        return redirect('product_list')

    return render(request, 'user/register.html')


# 2. 核心产品列表 (千人千面逻辑)
def product_list(request):
    products = Product.objects.all()
    user_recs = []  # 推荐
    in_stock = []  # 有货
    out_stock = []  # 无货

    # === 登录用户的特殊逻辑 ===
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        # A. 地区筛选 (功能点3: 01.01...-TW)
        if profile.country_suffix:
            # 筛选 SKU 包含该后缀的商品
            products = products.filter(sku__icontains=profile.country_suffix)

        # B. 屏蔽商品 (功能点5: 管理员设置不可见)
        if profile.blocked_product_keywords:
            keywords = profile.blocked_product_keywords.split(',')
            for kw in keywords:
                if kw.strip():
                    products = products.exclude(name__icontains=kw.strip())

        # C. 仓库权限计算 (功能点4: 可见仓库)
        # 我们不能直接用 p.total_qty，因为那包含了所有仓库
        # 我们需要手动算一遍
        allowed_warehouses = profile.allowed_warehouses

        # D. 获取管理员指定的推荐商品 (功能点6)
        user_recs = profile.recommended_products.all()

    # === 分类整理数据 (功能点2: 三种Tab) ===
    # 为了性能，这里做一次简单的内存分类，实际项目可以用更复杂的 QuerySet

    final_in_stock = []
    final_out_stock = []

    for p in products:
        # 计算该用户可见的库存
        if request.user.is_authenticated:
            # 如果是 ALL，直接取总数
            if not profile.allowed_warehouses or profile.allowed_warehouses == "ALL":
                visible_qty = p.total_qty
            else:
                # 只累加允许的仓库
                wh_list = [w.strip() for w in profile.allowed_warehouses.split(',')]
                # 这是一个跨表查询累加
                visible_qty = sum(s.qty for s in p.stocks.all() if s.warehouse in wh_list)
        else:
            # 必须用真实库存进行分类，否则会被全部分到缺货里
            visible_qty = p.total_qty

        # 动态给对象绑定一个属性，方便前端显示
        p.visible_qty = visible_qty

        # 找交期 (如果没货)
        if visible_qty <= 0:
            # 查 IncomingStock 表，找最近的一个交期
            incoming = IncomingStock.objects.filter(product=p).order_by('arrival_date').first()

            if incoming:
                p.next_arrival = incoming.arrival_date
                p.incoming_qty_display = incoming.qty  # 把在途的补货数量也抓出来
            else:
                p.next_arrival = "暂定 / TBD"
                p.incoming_qty_display = 0  # 如果没查到在途表，数量就是 0

            final_out_stock.append(p)
        else:
            # === 【关键修复】===
            # 如果库存大于0，必须把它加进有货的列表里！
            final_in_stock.append(p)

    context = {
        'recommended': user_recs if request.user.is_authenticated else products[:5],  # 游客默认显示前5个
        'in_stock': final_in_stock,
        'out_stock': final_out_stock,
        'show_login_modal': not request.user.is_authenticated  # 控制弹窗
    }
    return render(request, 'user/product_list.html', context)

# --- 新增：专门给管理员页面用的小接口 ---
@staff_member_required # 只有登录的管理员才能调这个接口，防止客户乱点
def get_new_order_count(request):
    # 统计状态为 'New' 的订单数量
    count = Order.objects.filter(status='New').count()
    return JsonResponse({'count': count})

# --- 模拟短信发送 ---
def send_sms_notification(customer_name):
    # 1. 找到所有管理员的电话
    admins = UserProfile.objects.filter(user__is_staff=True)
    for admin in admins:
        phone = admin.phone
        msg = f"【系统提醒】管理员您好，客户 {customer_name} 刚刚下了一个新订单，请去后台查看。"

        # 实际项目中，这里调用阿里云/腾讯云SDK
        print(f"=============================")
        print(f"模拟发送短信给 {phone}: {msg}")
        print(f"=============================")

# --- 新增：结算预览页面 (点击“去结算”后跳出的页面) ---
@require_POST
def checkout(request):
    """
    处理首页提交过来的批量选择，展示确认页让用户填信息
    """
    selected_items = []
    total_price = 0

    # 遍历提交的数据，寻找 'qty_产品ID' 格式的数据
    for key, value in request.POST.items():
        if key.startswith('qty_'):
            try:
                qty = int(value)
                if qty > 0:
                    product_id = key.split('_')[1]
                    product = Product.objects.get(id=product_id)
                    item_total = qty

                    selected_items.append({
                        'product': product,
                        'qty': qty,
                        'subtotal': item_total
                    })
                    total_price += item_total
            except ValueError:
                continue

    if not selected_items:
        # 如果没选东西，还是回首页
        return redirect('product_list')

    context = {
        'items': selected_items,
        'total_price': total_price
    }
    return render(request, 'user/checkout.html', context)


# --- 新增：最终确认下单 ---
@require_POST
def confirm_order(request):
    """
    保存订单和客户信息
    """
    # 1. 获取客户填写的信息
    name = request.POST.get('name')
    phone = request.POST.get('phone')
    email = request.POST.get('email')

    # 2. 创建订单对象
    order = Order.objects.create(
        customer=request.user if request.user.is_authenticated else None,  # 如果登录了就存账号，没登录存None
        guest_name=name,
        guest_phone=phone,
        guest_email=email,
        status='New'
    )

    # 3. 创建订单明细 (重新解析一遍提交的商品数据)
    #    注意：为了安全，实际项目中通常会用 Session 存购物车，
    #    这里为了简化，我们在 checkout.html 再次把数据传回来
    for key, value in request.POST.items():
        if key.startswith('final_qty_'):
            pid = key.split('_')[2]  # key格式: final_qty_123
            qty = int(value)
            OrderItem.objects.create(order=order, product_id=pid, quantity=qty)

    # 4. 发送通知
    send_sms_notification(name)
    # --- 邮件内容准备 ---
    subject = f"【新订单提醒】客户 {name} 刚刚下单了"

    # 构造邮件正文 (把买了什么也写进去)
    message = f"""
        管理员您好，

        客户姓名：{name}
        联系电话：{phone}
        电子邮箱：{email}

        下单商品清单：
        --------------------------
        """

    # 简单的把商品拼接到邮件里
    order_items = order.items.all()  # 假设您在 models.py 里 OrderItem 的 related_name='items'
    for item in order_items:
        message += f"{item.product.sku} (名称:{item.product.name}) x {item.quantity}\n"

    message += "\n请尽快登录后台处理。"

    # --- 发送动作 ---
    try:
        send_mail(
            subject,  # 标题
            message,  # 内容
            settings.DEFAULT_FROM_EMAIL,  # 发件人
            ['1154896649@qq.com'],  # <--- 收件人列表 (填您自己的邮箱)
            fail_silently=False,
        )
        print("邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")

    return render(request, 'user/order_success.html')

# --- 新增：自定义退出登录 ---
def custom_logout(request):
    logout(request)  # 清除用户的登录状态
    return redirect('product_list')  # 退出后自动跳回商品首页

# --- 新增：普通客户专属登录页面 ---
def user_login_view(request):
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        # authenticate 会去数据库核对账号密码，无论是不是管理员都能验证
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)  # 验证成功，执行登录
            return redirect('product_list')  # 登录后跳转到商品首页
        else:
            # 验证失败，返回错误信息
            return render(request, 'user/login.html', {'error': '账号或密码不正确，请重试'})

    # 如果是刚点进这个页面 (GET请求)，就显示登录框
    return render(request, 'user/login.html')