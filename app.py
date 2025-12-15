# -*- coding: utf-8 -*-
"""
校园二手交易系统 - Flask 后端主程序
功能模块：用户系统（注册/登录/资料管理/头像/学籍认证） + 商品发布/交易/订单全流程
数据库：MySQL (通过 pymysql 驱动)
作者：未知（典型校园二手交易平台后端）
"""
SYSTEM_USER_ID = 45  # ← 改成你查出来的id
from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash  # 安全哈希密码
from werkzeug.utils import secure_filename  # 安全处理上传文件名（本项目未使用，但导入保留）
import os
import random
import string
import datetime
from datetime import timedelta
import re  # 正则表达式，用于校验学号格式
from sqlalchemy import Integer, String, Text, DateTime  # 类型提示用（实际未使用，可删除）
from sqlalchemy.orm import joinedload
from sqlalchemy import or_  

# ==================== 内存锁（替代 Redis，防止超卖）===================
from collections import defaultdict
import time

# 使用全局字典模拟分布式锁，用于在高并发下防止商品库存超卖（开发/小项目神器）
# 键：goods_id → 值：{'quantity': 锁定的数量, 'expire': 过期时间戳}
_goods_lock = {}

def lock_stock(goods_id, quantity, seconds=600):
    """
    尝试锁定指定商品的指定数量库存
    :param goods_id: 商品ID
    :param quantity: 欲锁定的数量
    :param seconds: 锁超时时间（默认10分钟）
    :return: True=锁定成功，False=已被他人锁定
    """
    if goods_id in _goods_lock and time.time() < _goods_lock[goods_id]['expire']:
        return False  # 已被锁定
    _goods_lock[goods_id] = {'quantity': quantity, 'expire': time.time() + seconds}
    return True

def unlock_stock(goods_id):
    """支付成功或超时后释放库存锁"""
    _goods_lock.pop(goods_id, None)

# ====================== 应用初始化 ======================
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-for-dev')  # Flask session 加密密钥，生产环境必须改为随机强密钥！

# 数据库配置：使用 mysql+pymysql 驱动连接本地 MySQL
#app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/ershousystem?charset=utf8mb4'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') #or 'mysql+pymysql://root:123456@localhost/ershousystem?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # 关闭修改追踪功能（节省内存）

# 头像上传相关配置
app.config['UPLOAD_FOLDER'] = 'static/avatars/userspictures/'  # 头像保存目录
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 上传文件最大8MB，超大会返回413

# 初始化 SQLAlchemy 数据库实例
db = SQLAlchemy(app)

# 确保头像上传目录存在，不存在则自动创建
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ====================== 数据模型定义 ======================

class User(db.Model):
    """用户表"""
    __tablename__ = 'user'
    user_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)      # 主键自增
    account = db.Column(db.String(30), unique=True, nullable=False)               # 登录账号（学号/手机/邮箱）
    password = db.Column(db.String(100), nullable=False)                         # 存储哈希后的密码
    nickname = db.Column(db.String(50), nullable=False, server_default='校园用户')   # 昵称，默认“校园用户”
    avatar = db.Column(db.String(255), server_default='')                        # 头像路径
    email = db.Column(db.String(100))                                            # 邮箱，可为空
    stu_id = db.Column(db.String(20), unique=True)                               # 学号（唯一，用于实名认证）
    college = db.Column(db.String(50), server_default='')                        # 学院
    class_name = db.Column(db.String(50), server_default='')                     # 班级
    gender = db.Column(db.Integer, server_default='0')                           # 0=未填，1=男，2=女
    is_graduating = db.Column(db.Integer, server_default='0')                    # 是否应届毕业生 0=否 1=是
    status = db.Column(db.Integer, server_default='1')                           # 账号状态 1=正常 0=禁用
    reg_time = db.Column(db.DateTime, server_default=db.func.now())              # 注册时间
    is_admin = db.Column(db.Integer, server_default='0')

class Category(db.Model):
    __tablename__ = 'category'
    cate_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(30), nullable=False)
    sort = db.Column(db.Integer, server_default='0')
    enabled = db.Column(db.Boolean, server_default='1', default=True)  # 更稳妥

    def __repr__(self):
        return f'<Category {self.name}>'
    
class goods(db.Model):
    """商品表（注意类名小写，实际生产不推荐，但这里保持原样）"""
    __tablename__ = 'goods'
    goods_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    title = db.Column(db.String(100), nullable=False)           # 商品标题
    cate_id = db.Column(db.Integer, nullable=False)           # 分类ID
    user_id = db.Column(db.BigInteger, db.ForeignKey('user.user_id'), nullable=False)        # 发布者ID
    price = db.Column(db.DECIMAL(10,2), nullable=False)       # 价格，精确到分
    description = db.Column(db.Text)                          # 商品描述
    degree = db.Column(db.Integer, default=10)                # 新旧程度 10=全新
    stock = db.Column(db.Integer, default=1)                  # 库存数量
    status = db.Column(db.Integer, default=1)                 # 1=上架 0=下架
    is_batch = db.Column(db.Integer, default=0)               # 是否支持批量购买
    on_shelf_time = db.Column(db.DateTime, default=datetime.datetime.now)  # 上架时间
    view_num = db.Column(db.Integer, default=0)               # 浏览量
    wish_num = db.Column(db.Integer, default=0)               # 想买数
    favor_num = db.Column(db.Integer, default=0)              # 收藏数
    sold_num = db.Column(db.Integer, default=0)               # 已售数量
    user = db.relationship('User', backref='published_goods')

class goods_image(db.Model):
    """商品图片表"""
    __tablename__ = 'goods_image'
    img_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    goods_id = db.Column(db.BigInteger, nullable=False)       # 关联商品
    url = db.Column(db.String(255), nullable=False)           # 图片访问路径
    sort = db.Column(db.Integer, default=0)                   # 排序，第一张为封面

class Message(db.Model):
    """站内消息表"""
    __tablename__ = 'message'
    msg_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    from_user_id = db.Column(db.BigInteger, nullable=False)
    from_nickname = db.Column(db.String(50), default='系统')
    to_user_id = db.Column(db.BigInteger, nullable=False)
    order_id = db.Column(db.BigInteger)
    goods_id = db.Column(db.BigInteger)  # 新增
    type = db.Column(db.Enum('system', 'chat'), nullable=False, default='chat')
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Integer, server_default='0')
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class Order(db.Model):
    __tablename__ = 'order'
    order_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    order_no = db.Column(db.String(30), unique=True, nullable=False)
    buyer_id = db.Column(db.BigInteger, nullable=False)
    seller_id = db.Column(db.BigInteger, nullable=False)
    goods_id = db.Column(db.BigInteger, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    total_amount = db.Column(db.DECIMAL(10,2), nullable=False)
    pay_status = db.Column(db.Integer, default=0)  # 0待支付 1已支付 2已完成
    pay_time = db.Column(db.DateTime)
    confirm_time = db.Column(db.DateTime)          # ← 新增：确认收货时间
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    # 其他字段根据需要补充...

# ====================== 举报模型 ======================
class Report(db.Model):
    """举报表"""
    __tablename__ = 'report'
    
    report_id    = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    reporter_id  = db.Column(db.BigInteger, db.ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False)
    target_type  = db.Column(db.String(20), nullable=False)  # 'goods' 或 'user'（ENUM 在 SQLAlchemy 中用 String 模拟）
    target_id    = db.Column(db.BigInteger, nullable=False)
    reason       = db.Column(db.String(50), nullable=False)
    description  = db.Column(db.String(255), server_default='')
    evidence     = db.Column(db.String(255), server_default='')
    status = db.Column(db.Integer, server_default='0')  # 正确！推荐
    created_at   = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    # 关系（方便查询举报人信息）
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='reports')


from flask import g  # 加上这行
# ====================== 登录验证装饰器 ======================
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify(code=401, msg='请先登录')
        g.user_id = session['user_id']  # 可选
        return f(*args, **kwargs)
    return decorated_function


# ====================== 路由定义 ======================

@app.route('/')
def index():
    """网站首页：支持关键词搜索 + 分类过滤 + 智能隐藏推荐区"""
    user = None
    unread_count = 0

    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        unread_count = db.session.execute(
            db.text("SELECT COUNT(*) FROM message WHERE to_user_id = :uid AND is_read = 0"),
            {'uid': session['user_id']}
        ).scalar() or 0

    # 获取参数
    keyword = request.args.get('keyword', '').strip()
    cate_id = request.args.get('cate_id', type=int)

    current_category = None
    if cate_id:
        current_category = Category.query.get(cate_id)

    categories = Category.query.filter_by(enabled=1).order_by(Category.sort).all()

    # 是否处于搜索模式
    is_search_mode = bool(keyword)

    # 基础 SQL（用于推荐区和搜索结果）
    base_sql = f"""
        SELECT 
            g.goods_id, g.title, g.price, g.degree, g.favor_num, g.view_num, g.is_batch,
            u.nickname AS user_nickname,
            gi.url AS cover_img
        FROM goods g
        LEFT JOIN user u ON g.user_id = u.user_id
        LEFT JOIN goods_image gi ON gi.goods_id = g.goods_id AND gi.sort = 0
        WHERE g.status = 1
    """
    params = {}
    conditions = []

    # 关键词搜索（标题或描述）
    if keyword:
        conditions.append("(g.title LIKE :keyword OR g.description LIKE :keyword)")
        params['keyword'] = f"%{keyword}%"

    # 分类过滤
    if cate_id:
        conditions.append("g.cate_id = :cate_id")
        params['cate_id'] = cate_id

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)

    hot_expr_str = "(g.favor_num * 5 + g.wish_num * 3 + g.view_num + g.sold_num * 10)"

    # 如果是搜索模式 → 不显示四大推荐区，只显示搜索结果
    if is_search_mode:
        search_sql = f"{base_sql} ORDER BY {hot_expr_str} DESC LIMIT 50"
        search_goods = db.session.execute(db.text(search_sql), params).fetchall()
        search_goods = [dict(row._mapping) for row in search_goods]

        default_cover = '/static/avatars/goodspictures/default.jpg'
        for g in search_goods:
            g['cover_img'] = g['cover_img'] or default_cover
            g['user_nickname'] = g['user_nickname'] or '未知用户'

        return render_template('visiter/index.html',
                               user=user,
                               categories=categories,
                               current_category=current_category,
                               keyword=keyword,
                               search_goods=search_goods,  # 搜索结果
                               unread_count=unread_count)

    # 非搜索模式：显示四大推荐区（受分类过滤）
    else:
        # 热门推荐
        hot_goods = db.session.execute(db.text(f"{base_sql} ORDER BY {hot_expr_str} DESC LIMIT 12"), params).fetchall()

        # 最新上架
        newest_goods = db.session.execute(db.text(f"{base_sql} ORDER BY g.on_shelf_time DESC LIMIT 12"), params).fetchall()

        # 应届毕业生清仓
        batch_sql = f"{base_sql} AND g.is_batch = 1 AND u.is_graduating = 1 ORDER BY {hot_expr_str} DESC LIMIT 12"
        batch_goods = db.session.execute(db.text(batch_sql), params).fetchall()

        # 本院热销
        same_college_goods = []
        if user and user.college:
            college_sql = f"{base_sql} AND u.college = :college ORDER BY {hot_expr_str} DESC LIMIT 12"
            same_college_goods = db.session.execute(
                db.text(college_sql),
                {**params, 'college': user.college}
            ).fetchall()

        default_cover = '/static/avatars/goodspictures/default.jpg'
        def process(rows):
            result = [dict(row._mapping) for row in rows]
            for item in result:
                item['cover_img'] = item['cover_img'] or default_cover
                item['user_nickname'] = item['user_nickname'] or '未知用户'
            return result

        hot_goods = process(hot_goods)
        newest_goods = process(newest_goods)
        batch_goods = process(batch_goods)
        same_college_goods = process(same_college_goods)

        return render_template('visiter/index.html',
                               user=user,
                               categories=categories,
                               current_category=current_category,
                               hot_goods=hot_goods if hot_goods else None,
                               newest_goods=newest_goods if newest_goods else None,
                               batch_goods=batch_goods if batch_goods else None,
                               same_college_goods=same_college_goods if same_college_goods else None,
                               unread_count=unread_count)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册路由：GET 显示注册页，POST 处理注册逻辑"""
    if request.method == 'POST':
        try:
            raw_data = request.get_json(force=True)  # 强制解析 JSON，防止前端传错
            data = raw_data if isinstance(raw_data, dict) else {}

            account = data.get('account', '').strip()
            password = data.get('password', '')
            nickname = data.get('nickname', '').strip() or '校园用户'
            email = data.get('email', '').strip() or None

            # 基础校验
            if not account:
                return jsonify(code=400, msg='账号不能为空')
            if not password:
                return jsonify(code=400, msg='密码不能为空')
            if len(password) < 6:
                return jsonify(code=400, msg='密码至少6位')
            if User.query.filter_by(account=account).first():
                return jsonify(code=400, msg='账号已存在')

            # 创建新用户，密码使用 werkzeug 安全哈希
            new_user = User(
                account=account,
                password=generate_password_hash(password),
                nickname=nickname,
                email=email
            )
            db.session.add(new_user)
            db.session.commit()
            return jsonify(code=200, msg='注册成功！请登录')

        except Exception as e:
            db.session.rollback()
            print("【注册失败】", str(e))
            return jsonify(code=500, msg='服务器异常，请稍后重试')

    return render_template('visiter/register.html')  # GET 请求返回注册页面


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录路由"""
    if request.method == 'POST':
        try:
            raw_data = request.get_json(force=True)
            data = raw_data if isinstance(raw_data, dict) else {}

            account = data.get('account', '').strip()
            password = data.get('password', '')

            if not account or not password:
                return jsonify(code=400, msg='请输入账号和密码')

            user = User.query.filter_by(account=account).first()
            if not user:
                return jsonify(code=400, msg='账号不存在')
            if not check_password_hash(user.password, password):
                return jsonify(code=400, msg='密码错误')
            if user.status == 0:
                return jsonify(code=403, msg='账号已被禁用')
            
            session.clear()  # ← 关键：完全清除旧 session
            # 登录成功 → 写入 session
            session['user_id'] = user.user_id
            return jsonify(code=200, msg='登录成功')

        except Exception as e:
            print("【登录失败】", str(e))
            return jsonify(code=500, msg='服务器异常')

    return render_template('visiter/login.html')


@app.route('/profile')
@login_required
def profile():
    """个人中心页面"""
    user = User.query.get(session['user_id'])

    # 统计用户发布的商品数、订单数、收藏数、想买数（原生 SQL 更快）
    goods_count = db.session.execute(
        db.text("SELECT COUNT(*) FROM goods WHERE user_id = :uid"),
        {'uid': user.user_id}
    ).scalar() or 0

    order_count = db.session.execute(
        db.text("SELECT COUNT(*) FROM `order` WHERE buyer_id = :uid"),
        {'uid': user.user_id}
    ).scalar() or 0

    favor_count = db.session.execute(
        db.text("SELECT COUNT(*) FROM user_interaction WHERE user_id = :uid AND type = 1"),
        {'uid': user.user_id}
    ).scalar() or 0

    wish_count = db.session.execute(
        db.text("SELECT COUNT(*) FROM user_interaction WHERE user_id = :uid AND type = 2"),
        {'uid': user.user_id}
    ).scalar() or 0

    return render_template('visiter/profile.html', user=user, stats={
        'goods': goods_count,
        'orders': order_count,
        'favors': favor_count,
        'wishes': wish_count
    })


@app.route('/api/auth/student', methods=['POST'])
@login_required
def auth_student():
    """学籍认证接口（绑定学号）"""
    data = request.get_json()
    user = User.query.get(session['user_id'])

    if User.query.filter_by(stu_id=data['stu_id']).first():
        return jsonify(code=400, msg='学号已被绑定')

    if not re.match(r'^\d{8,12}$', data['stu_id']):
        return jsonify(code=400, msg='学号格式错误（8~12位纯数字）')

    user.stu_id = data['stu_id']
    user.is_graduating = 1 if data.get('is_graduating') else 0
    db.session.commit()
    return jsonify(code=200, msg='认证成功')


@app.route('/api/upload/avatar', methods=['POST'])
@login_required
def upload_avatar():
    """头像上传接口"""
    if 'file' not in request.files:
        return jsonify(code=400, msg='未选择文件')
    file = request.files['file']
    if file.filename == '':
        return jsonify(code=400, msg='未选择文件')

    # 只允许常见图片格式
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in {'png', 'jpg', 'jpeg', 'gif'}:
        return jsonify(code=400, msg='仅支持图片格式')

    # 使用 user_id + 时间戳 生成唯一文件名，防止覆盖
    filename = f"{session['user_id']}_{int(datetime.datetime.now().timestamp())}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # 更新用户表中的头像字段
    user = User.query.get(session['user_id'])
    user.avatar = f"/static/avatars/{filename}"
    db.session.commit()
    return jsonify(code=200, url=user.avatar, msg='上传成功')


@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    """更新个人资料（昵称、学院、班级、性别）"""
    data = request.get_json()
    user = User.query.get(session['user_id'])

    allowed_fields = {'nickname': str, 'college': str, 'class_name': str}
    for field, _ in allowed_fields.items():
        if field in data:
            value = data[field].strip() if isinstance(data[field], str) else None
            setattr(user, field, value or None)

    if 'gender' in data:
        try:
            g = int(data['gender'])
            if g not in (0,1,2):
                raise ValueError
            user.gender = g
        except:
            return jsonify(code=400, msg='性别参数无效')

    db.session.commit()
    return jsonify(code=200, msg='资料更新成功')


@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/static/avatars/<filename>')
def avatar(filename):
    """安全提供头像访问路由（不直接暴露整个 static 目录）"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ====================== 商品相关路由 ======================

@app.route('/goods/<int:goods_id>')
def goods_detail(goods_id):
    """商品详情页"""
    goods = db.session.execute(db.text("""
        SELECT g.*, c.name as cate_name,
               (SELECT url FROM goods_image WHERE goods_id=g.goods_id ORDER BY sort LIMIT 1) as cover_img
        FROM goods g 
        LEFT JOIN category c ON g.cate_id = c.cate_id
        WHERE g.goods_id = :gid AND g.status = 1
    """), {'gid': goods_id}).fetchone()

    if not goods:
        return "商品不存在或已下架", 404

    # 商品所有图片
    images = db.session.execute(db.text("""
        SELECT url FROM goods_image WHERE goods_id = :gid ORDER BY sort
    """), {'gid': goods_id}).fetchall()

    # 卖家信息
    seller = User.query.get(goods.user_id)

    # 当前登录用户是否已想买/收藏该商品
    user = None
    is_wish = is_favor = False
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        interact = db.session.execute(db.text("""
            SELECT type FROM user_interaction 
            WHERE user_id = :uid AND goods_id = :gid
        """), {'uid': session['user_id'], 'gid': goods_id}).fetchall()
        for row in interact:
            if row.type == 2: is_wish = True
            if row.type == 1: is_favor = True

    return render_template('visiter/goods_detail.html',
                           goods=goods,
                           images=images,
                           seller=seller,
                           user=user,
                           is_wish=is_wish,
                           is_favor=is_favor)


@app.route('/api/goods/<int:goods_id>/view', methods=['POST'])
def add_view(goods_id):
    """增加商品浏览量"""
    db.session.execute(db.text("""
        UPDATE goods SET view_num = view_num + 1 WHERE goods_id = :gid
    """), {'gid': goods_id})
    db.session.commit()
    return jsonify(code=200)


@app.route('/api/interact/<action>', methods=['POST'])
@login_required
def interact(action):
    """想买 / 收藏 统一接口（action = wish 或 favor）"""
    data = request.get_json()
    gid = data.get('goods_id')
    if not gid:
        return jsonify(code=400, msg='参数错误')

    type_map = {'wish': 2, 'favor': 1}
    if action not in type_map:
        return jsonify(code=404, msg='操作不存在')

    t = type_map[action]
    existed = db.session.execute(db.text("""
        SELECT id FROM user_interaction 
        WHERE user_id = :uid AND goods_id = :gid AND type = :t
    """), {'uid': session['user_id'], 'gid': gid, 't': t}).fetchone()

    if existed:
        # 已存在 → 取消操作
        db.session.execute(db.text("""
            DELETE FROM user_interaction 
            WHERE user_id = :uid AND goods_id = :gid AND type = :t
        """), {'uid': session['user_id'], 'gid': gid, 't': t})
        db.session.execute(db.text(f"""
            UPDATE goods SET {'wish_num' if t==2 else 'favor_num'} = 
            GREATEST(0, {'wish_num' if t==2 else 'favor_num'} - 1)
            WHERE goods_id = :gid
        """), {'gid': gid})
        is_current = False
    else:
        # 不存在 → 添加
        db.session.execute(db.text("""
            INSERT INTO user_interaction (user_id, goods_id, type) 
            VALUES (:uid, :gid, :t)
        """), {'uid': session['user_id'], 'gid': gid, 't': t})
        db.session.execute(db.text(f"""
            UPDATE goods SET {'wish_num' if t==2 else 'favor_num'} = 
            {'wish_num' if t==2 else 'favor_num'} + 1
            WHERE goods_id = :gid
        """), {'gid': gid})
        is_current = True

    db.session.commit()
    return jsonify(code=200, data={'is_wish' if t==2 else 'is_favor': is_current})


@app.route('/publish')
@login_required
def publish_page():
    """发布商品页面"""
    categories = db.session.execute(db.text("SELECT cate_id, name FROM category WHERE enabled=1")).fetchall()
    user = User.query.get(session['user_id'])
    return render_template('visiter/goods_publish.html', user=user, categories=categories)


@app.route('/api/goods/publish', methods=['POST'])
@login_required
def api_publish_goods():
    """商品发布核心接口（支持多图上传）"""
    try:
        title = request.form['title']
        price = float(request.form['price'])
        cate_id = int(request.form['cate_id'])
        degree = int(request.form['degree'])
        description = request.form.get('description', '')
        is_batch = 1 if request.form.get('is_batch') == '1' else 0

        # 创建商品记录
        new_goods = goods(
            title=title, cate_id=cate_id, user_id=session['user_id'],
            price=price, description=description, degree=degree,
            stock=1, status=1, is_batch=is_batch
        )
        db.session.add(new_goods)
        db.session.flush()  # 获取自增 goods_id

        # 处理图片上传（最多9张）
        upload_folder = 'static/avatars/goodspictures'
        os.makedirs(upload_folder, exist_ok=True)
        files = request.files.getlist('images')
        if not files or len(files) == 0:
            return jsonify(code=400, msg='请上传至少一张图片')

        for i, file in enumerate(files[:9]):
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                filename = f"{new_goods.goods_id}_{i}.{ext}"
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)

                img = goods_image(
                    goods_id=new_goods.goods_id,
                    url=f"/static/avatars/goodspictures/{filename}",
                    sort=i
                )
                db.session.add(img)

        db.session.commit()
        return jsonify(code=200, msg='发布成功！', goods_id=new_goods.goods_id)

    except Exception as e:
        db.session.rollback()
        print("【发布失败】", str(e))
        return jsonify(code=500, msg='服务器错误：' + str(e))




@app.route('/api/goods/list')
def api_goods_list():
    keyword = request.args.get('keyword', '').strip()
    cate_id = request.args.get('cate_id', type=int)
    price_min = request.args.get('price_min', type=float)
    price_max = request.args.get('price_max', type=float)
    degree_min = request.args.get('degree_min', type=int)
    only_graduating = request.args.get('only_graduating', '0') == '1'
    same_college = request.args.get('same_college', '0') == '1'
    sort = request.args.get('sort', 'default')
    page = max(1, request.args.get('page', 1, type=int))
    page_size = 20

    # 注意这里用小写的 goods
    query = goods.query.options(joinedload(goods.user)).filter(goods.status == 1)

    if keyword:
        query = query.filter(
            (goods.title.ilike(f'%{keyword}%')) |
            (goods.description.ilike(f'%{keyword}%'))
        )

    if cate_id:
        query = query.filter(goods.cate_id == cate_id)

    if price_min is not None:
        query = query.filter(goods.price >= price_min)
    if price_max is not None:
        query = query.filter(goods.price <= price_max)

    if degree_min is not None:
        query = query.filter(goods.degree >= degree_min)

    if only_graduating:
        query = query.join(User).filter(User.is_graduating == 1, goods.is_batch == 1)

    if same_college and 'user_id' in session:
        current_user = User.query.get(session['user_id'])
        if current_user and current_user.college:
            query = query.join(User).filter(User.college == current_user.college)

    # 热度公式
    hot_expr = goods.favor_num * 5 + goods.wish_num * 3 + goods.view_num + goods.sold_num * 10

    if sort == 'newest':
        query = query.order_by(goods.on_shelf_time.desc())
    elif sort == 'price_asc':
        query = query.order_by(goods.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(goods.price.desc())
    elif sort == 'hot':
        query = query.order_by(hot_expr.desc())
    else:
        query = query.order_by(goods.on_shelf_time.desc(), hot_expr.desc())

    total = query.count()
    goods_list = query.offset((page-1)*page_size).limit(page_size).all()

    data = []
    for g in goods_list:
        cover = goods_image.query.filter_by(goods_id=g.goods_id).order_by(goods_image.sort).first()
        data.append({
            'goods_id': g.goods_id,
            'title': g.title,
            'price': float(g.price),
            'cover_img': cover.url if cover else '/static/avatars/goodspictures/default.jpg',
            'degree': g.degree,
            'view_num': g.view_num,
            'wish_num': g.wish_num,
            'favor_num': g.favor_num,
            'sold_num': g.sold_num,
            'is_batch': g.is_batch,
            'user_nickname': g.user.nickname if g.user else '未知用户',
            'user_college': g.user.college if g.user else '',
        })

    return jsonify(code=200, data=data, total=total, page=page)

# ====================== 我的页面相关 ======================
@app.route('/my')
@login_required
def my():
    user = User.query.get(session['user_id'])
    return render_template('visiter/my.html', user=user)

@app.route('/api/my/publish')
@login_required
def api_my_publish():
    uid = session['user_id']
    rows = db.session.execute(db.text("""
        SELECT g.goods_id, g.title, g.price, g.status,
               (SELECT url FROM goods_image WHERE goods_id=g.goods_id ORDER BY sort LIMIT 1) as cover_img
        FROM goods g 
        WHERE g.user_id = :uid
        ORDER BY g.on_shelf_time DESC
    """), {'uid': uid}).fetchall()

    result = []
    for r in rows:
        item = dict(r._mapping)
        item['price'] = float(item['price'])
        result.append(item)
    return jsonify(data=result)

@app.route('/api/my/wish')
@login_required
def api_my_wish():
    uid = session['user_id']
    rows = db.session.execute(db.text("""
        SELECT g.goods_id, g.title, g.price, g.status,
               (SELECT url FROM goods_image WHERE goods_id=g.goods_id ORDER BY sort LIMIT 1) as cover_img
        FROM goods g 
        JOIN user_interaction ui ON g.goods_id = ui.goods_id
        WHERE ui.user_id = :uid AND ui.type = 2
        ORDER BY ui.created_at DESC
    """), {'uid': uid}).fetchall()

    result = []
    for r in rows:
        item = dict(r._mapping)
        item['price'] = float(item['price'])
        result.append(item)
    return jsonify(data=result)

@app.route('/api/my/favor')
@login_required
def api_my_favor():
    uid = session['user_id']
    rows = db.session.execute(db.text("""
        SELECT g.goods_id, g.title, g.price, g.status,
               (SELECT url FROM goods_image WHERE goods_id=g.goods_id ORDER BY sort LIMIT 1) as cover_img
        FROM goods g 
        JOIN user_interaction ui ON g.goods_id = ui.goods_id
        WHERE ui.user_id = :uid AND ui.type = 1
        ORDER BY ui.created_at DESC
    """), {'uid': uid}).fetchall()

    result = []
    for r in rows:
        item = dict(r._mapping)
        item['price'] = float(item['price'])
        result.append(item)
    return jsonify(data=result)


# ====================== 订单与支付流程 ======================
def generate_order_no():
    """生成18位纯数字订单号"""
    return ''.join(random.choices(string.digits, k=18))

@app.route('/order/create')
@login_required
def order_create_page():
    """下单页面"""
    goods_id = request.args.get('goods_id', type=int)
    if not goods_id:
        return "参数错误", 400
    
    goods_info = db.session.execute(db.text("""
        SELECT g.*, c.name as cate_name,
               (SELECT url FROM goods_image WHERE goods_id=g.goods_id ORDER BY sort LIMIT 1) as cover_img
        FROM goods g 
        LEFT JOIN category c ON g.cate_id=c.cate_id 
        WHERE g.goods_id=:gid AND g.status=1 AND g.stock>0
    """), {'gid': goods_id}).fetchone()
    
    if not goods_info:
        return "商品不存在或已下架", 404
        
    return render_template('visiter/order_create.html', goods=goods_info, user=User.query.get(session['user_id']))

@app.route('/api/order/create', methods=['POST'])
@login_required
def api_order_create():
    """创建订单 + 内存锁库存"""
    try:
        data = request.get_json()
        goods_id = data['goods_id']
        quantity = int(data.get('quantity', 1))

        # 校验商品是否存在且库存足够
        goods_info = db.session.execute(db.text("""
            SELECT goods_id, user_id, title, price, stock FROM goods 
            WHERE goods_id=:gid AND status=1 AND stock>=:qty
        """), {'gid': goods_id, 'qty': quantity}).fetchone()

        if not goods_info:
            return jsonify(code=400, msg='商品不存在或库存不足')

        # 使用内存锁防止超卖
        if not lock_stock(goods_id, quantity):
            return jsonify(code=400, msg='商品正在被购买，请稍后再试')

        order_no = generate_order_no()
        order = {
            'order_no': order_no,
            'goods_id': goods_id,
            'buyer_id': session['user_id'],
            'seller_id': goods_info.user_id,
            'quantity': quantity,
            'buy_price': goods_info.price,
            'total_amount': goods_info.price * quantity,
            'pay_status': 0
        }
        
        db.session.execute(db.text("""
            INSERT INTO `order` 
            (order_no, goods_id, buyer_id, seller_id, quantity, buy_price, total_amount, pay_status)
            VALUES (:order_no, :goods_id, :buyer_id, :seller_id, :quantity, :buy_price, :total_amount, 0)
        """), order)
        db.session.commit()
        
        return jsonify(code=200, msg='订单创建成功', order_no=order_no)

    except Exception as e:
        db.session.rollback()
        print("【创建订单失败】", str(e))
        return jsonify(code=500, msg='服务器错误')

@app.route('/api/order/pay/<order_no>', methods=['POST'])
@login_required
def api_order_pay(order_no):
    """虚拟支付接口（模拟支付成功） - 加入超时判断"""
    try:
        # 查询订单，必须是当前用户、待支付状态
        order = db.session.execute(db.text("""
            SELECT o.*, g.stock AS current_stock 
            FROM `order` o
            JOIN goods g ON o.goods_id = g.goods_id
            WHERE o.order_no = :no 
              AND o.buyer_id = :uid 
              AND o.pay_status = 0
        """), {'no': order_no, 'uid': session['user_id']}).fetchone()

        if not order:
            return jsonify(code=400, msg='订单不存在、已支付或无权限')

        # ==================== 关键：超时判断 ====================
        # 订单创建时间 + 1小时
        deadline = order.created_at + timedelta(hours=1)
        if datetime.datetime.now() > deadline:
            # 标记为已取消（建议数据库支持 pay_status=3）
            db.session.execute(db.text("""
                UPDATE `order` 
                SET pay_status = 3, cancel_time = NOW(), cancel_reason = '支付超时自动取消'
                WHERE order_no = :no
            """), {'no': order_no})

            # 释放内存锁
            unlock_stock(order.goods_id)

            # 可选：恢复商品库存（更准确，避免超卖遗留）
            db.session.execute(db.text("""
                UPDATE goods 
                SET stock = stock + :qty 
                WHERE goods_id = :gid AND stock + :qty <= (sold_num + stock + :qty)  -- 防止异常
            """), {'qty': order.quantity, 'gid': order.goods_id})

            db.session.commit()
            return jsonify(code=400, msg='订单支付超时，已自动取消，请重新下单')

        # ==================== 正常支付流程 ====================
        # 标记为已支付
        db.session.execute(db.text("""
            UPDATE `order` 
            SET pay_status = 1, pay_time = NOW() 
            WHERE order_no = :no
        """), {'no': order_no})

        # 真正扣减库存 + 增加销量
        db.session.execute(db.text("""
            UPDATE goods 
            SET stock = stock - :qty, 
                sold_num = sold_num + :qty
            WHERE goods_id = :gid
        """), {'qty': order.quantity, 'gid': order.goods_id})

        # 如果库存扣为0或负，自动标记商品为已售（status=2）
        db.session.execute(db.text("""
            UPDATE goods 
            SET status = CASE 
                WHEN stock <= 0 THEN 2  -- 已售罄
                ELSE status 
            END
            WHERE goods_id = :gid
        """), {'gid': order.goods_id})

        db.session.commit()

        # 释放内存锁（支付成功或超时都应释放）
        unlock_stock(order.goods_id)

        # 获取最新信息用于发消息
        goods = db.session.execute(db.text("""
            SELECT title FROM goods WHERE goods_id = :gid
        """), {'gid': order.goods_id}).fetchone()

        # 发送系统消息
        send_message(order.buyer_id, f"您已成功支付订单 {order_no} 的商品《{goods.title}》，请尽快联系卖家当面交易~")
        send_message(order.seller_id, f"买家已成功支付订单 {order_no} 的商品《{goods.title}》，请及时与买家联系！")

        return jsonify(code=200, msg='支付成功')

    except Exception as e:
        db.session.rollback()
        print("【支付失败】", str(e))
        return jsonify(code=500, msg='支付失败，请重试')

@app.route('/api/order/confirm/<order_no>', methods=['POST'])
@login_required
def api_order_confirm(order_no):
    """买家确认收货"""
    order = db.session.execute(db.text("""
        SELECT * FROM `order` WHERE order_no=:no AND buyer_id=:uid AND pay_status=1
    """), {'no': order_no, 'uid': session['user_id']}).fetchone()
    
    if not order:
        return jsonify(code=400, msg='订单状态错误')
    
    db.session.execute(db.text("""
        UPDATE `order` SET pay_status=2, confirm_time=NOW() WHERE order_no=:no
    """), {'no': order_no})
    db.session.commit()
    order = db.session.execute(db.text("SELECT * FROM `order` WHERE order_no=:no"), {'no': order_no}).fetchone()
    goods = db.session.execute(db.text("SELECT title FROM goods WHERE goods_id=:gid"), {'gid': order.goods_id}).fetchone()

    send_message(order.seller_id, f"买家已确认收货，订单 {order_no} 《{goods.title}》交易完成！")
    send_message(order.buyer_id, f"您已确认收货，订单 {order_no} 《{goods.title}》交易完成，感谢使用！")
    return jsonify(code=200, msg='交易完成')

@app.route('/api/my/order')
@login_required
def api_my_orders():
    """我的订单列表（买家+卖家订单都显示）"""
    status_filter = request.args.get('status', 'all')
    uid = session['user_id']
    
    where = "(o.buyer_id=:uid OR o.seller_id=:uid)"
    params = {'uid': uid}
    if status_filter != 'all':
        params['pay_status'] = int(status_filter)
        where += " AND o.pay_status=:pay_status"

    sql = f"""
        SELECT 
            o.order_no, o.goods_id, o.quantity, o.total_amount, o.pay_status,
            g.title, g.price,
            (SELECT url FROM goods_image WHERE goods_id=o.goods_id ORDER BY sort LIMIT 1) AS cover_img,
            seller.nickname AS seller_nick, buyer.nickname AS buyer_nick,
            seller.user_id AS seller_id, buyer.user_id AS buyer_id
        FROM `order` o
        JOIN goods g ON o.goods_id = g.goods_id
        JOIN user seller ON o.seller_id = seller.user_id
        JOIN user buyer ON o.buyer_id = buyer.user_id
        WHERE {where}
        ORDER BY o.created_at DESC
        LIMIT 100
    """
    rows = db.session.execute(db.text(sql), params).fetchall()
    
    result = []
    for r in rows:
        item = dict(r._mapping)
        item['total_amount'] = float(item['total_amount']) if item['total_amount'] else 0
        result.append(item)
    
    return jsonify(data=result)  # 前端必须用 data 字段接收


@app.route('/api/goods/off', methods=['POST'])
@login_required
def off_goods():
    """上架/下架自己的商品"""
    data = request.get_json()
    gid = data.get('goods_id')
    status = data.get('status')
    if not gid or status not in (0,1):
        return jsonify(code=400, msg='参数错误')
    db.session.execute(db.text("""
        UPDATE goods SET status=:status 
        WHERE goods_id=:gid AND user_id=:uid
    """), {'status': status, 'gid': gid, 'uid': session['user_id']})
    db.session.commit()
    return jsonify(code=200, msg='操作成功')


@app.route('/order/<order_no>')
@login_required
def order_detail(order_no):
    """订单详情页"""
    sql = """
        SELECT 
            o.order_id,                  -- ← 新增：主键 order_id，用于聊天跳转
            o.order_no, 
            o.quantity, 
            o.total_amount, 
            o.pay_status,
            o.created_at, 
            o.pay_time, 
            o.confirm_time,
            g.title, 
            g.price AS goods_price,
            (SELECT url FROM goods_image WHERE goods_id = o.goods_id ORDER BY sort LIMIT 1) AS cover_img,
            u1.nickname AS seller_nick,
            u1.avatar AS seller_avatar,   -- 可选：如果想显示对方头像
            u2.nickname AS buyer_nick,
            u2.avatar AS buyer_avatar,     -- 可选
            u1.user_id AS seller_id,
            u2.user_id AS buyer_id
        FROM `order` o
        JOIN goods g ON o.goods_id = g.goods_id
        JOIN user u1 ON o.seller_id = u1.user_id
        JOIN user u2 ON o.buyer_id = u2.user_id
        WHERE o.order_no = :no 
          AND (o.buyer_id = :uid OR o.seller_id = :uid)
    """
    order_row = db.session.execute(db.text(sql), {'no': order_no, 'uid': session['user_id']}).fetchone()
    
    if not order_row:
        return "订单不存在或无权查看", 404
    
    # 转为字典，方便模板使用
    order = dict(order_row._mapping)
    
    # 必要的类型转换
    order['total_amount'] = float(order['total_amount'] or 0)
    order['quantity'] = int(order['quantity'] or 1)
    
    # pay_status 为 int，确保模板判断正常
    order['pay_status'] = int(order['pay_status'])

    current_user = User.query.get(session['user_id'])
    
    return render_template('visiter/order_detail.html', 
                           order=order, 
                           user=current_user)

# ====================== 评论系统：发表评论（支持回复） ======================
@app.route('/api/comment/publish', methods=['POST'])
@login_required
def api_comment_publish():
    data = request.get_json() or {}
    goods_id = data.get('goods_id')
    content = data.get('content', '').strip()
    parent_id = int(data.get('parent_id', 0))

    if not goods_id or not content:
        return jsonify(code=400, msg='内容不能为空')

    if len(content) > 500:
        return jsonify(code=400, msg='评论最多500字')

    # 检查商品是否存在
    g_count = db.session.execute(
        db.text("SELECT 1 FROM goods WHERE goods_id=:gid AND status=1"),
        {'gid': goods_id}
    ).fetchone()
    if not g_count:
        return jsonify(code=404, msg='商品不存在或已下架')

    try:
        db.session.execute(db.text("""
            INSERT INTO comment (goods_id, user_id, parent_id, content)
            VALUES (:gid, :uid, :pid, :content)
        """), {
            'gid': goods_id,
            'uid': session['user_id'],
            'pid': parent_id,
            'content': content
        })
        db.session.commit()
        return jsonify(code=200, msg='评论成功')
    except Exception as e:
        db.session.rollback()
        print("评论失败:", e)
        return jsonify(code=500, msg='服务器错误')


# ====================== 评论系统：点赞/取消点赞 ======================
@app.route('/api/comment/like', methods=['POST'])
@login_required
def api_comment_like():
    data = request.get_json()
    comment_id = data.get('comment_id')
    if not comment_id:
        return jsonify(code=400, msg='参数错误')

    uid = session['user_id']

    # 检查是否已点赞
    existed = db.session.execute(db.text("""
        SELECT id FROM comment_like 
        WHERE comment_id=:cid AND user_id=:uid
    """), {'cid': comment_id, 'uid': uid}).fetchone()

    if existed:
        # 取消点赞
        db.session.execute(db.text("""
            DELETE FROM comment_like 
            WHERE comment_id=:cid AND user_id=:uid
        """), {'cid': comment_id, 'uid': uid})
        db.session.execute(db.text("""
            UPDATE comment SET like_count = GREATEST(0, like_count - 1)
            WHERE comment_id=:cid
        """), {'cid': comment_id})
        action = 'cancel'
    else:
        # 点赞
        db.session.execute(db.text("""
            INSERT INTO comment_like (comment_id, user_id) VALUES (:cid, :uid)
        """), {'cid': comment_id, 'uid': uid})
        db.session.execute(db.text("""
            UPDATE comment SET like_count = like_count + 1 
            WHERE comment_id=:cid
        """), {'cid': comment_id})
        action = 'like'

        # 通知评论作者（不是自己点的才通知）
        author = db.session.execute(db.text("""
            SELECT user_id FROM comment WHERE comment_id=:cid
        """), {'cid': comment_id}).fetchone()
        if author and author.user_id != uid:
            db.session.execute(db.text("""
                INSERT INTO message (from_user_id, to_user_id, goods_id, content, type)
                VALUES (:from, :to, (SELECT goods_id FROM comment WHERE comment_id=:cid), '有人点赞了你的评论', 'comment_like')
            """), {'from': uid, 'to': author.user_id})

    db.session.commit()

    new_count = db.session.execute(db.text("""
        SELECT like_count FROM comment WHERE comment_id=:cid
    """), {'cid': comment_id}).scalar()

    return jsonify(code=200, action=action, like_count=new_count)


# ====================== 评论系统：获取评论列表（已存在，但补全一下更稳） ======================
@app.route('/api/comment/list')
def api_comment_list():
    goods_id = request.args.get('goods_id', type=int)
    if not goods_id:
        return jsonify(code=400, msg='参数错误')

    uid = session.get('user_id', 0)

    sql = """
        SELECT 
            c.comment_id,
            c.parent_id,
            c.content,
            c.created_at,
            c.like_count,
            u.user_id,
            u.nickname,
            u.avatar,
            CASE WHEN cl.user_id IS NOT NULL THEN 1 ELSE 0 END AS is_liked
        FROM comment c
        JOIN user u ON c.user_id = u.user_id
        LEFT JOIN comment_like cl ON cl.comment_id = c.comment_id AND cl.user_id = :uid
        WHERE c.goods_id = :gid
        ORDER BY c.created_at ASC   -- 先旧后新，保证父节点先出现
    """
    rows = db.session.execute(db.text(sql), {'gid': goods_id, 'uid': uid}).fetchall()

    # 关键修复：两遍循环法，彻底杜绝掉层！
    comment_map = {}
    root_comments = []

    # 第一遍：把所有评论都放进 map，无论有没有父节点
    for row in rows:
        comment = {
            'comment_id': row.comment_id,
            'parent_id': row.parent_id or 0,
            'content': row.content,
            'created_at': row.created_at.strftime('%Y-%m-%d %H:%M'),
            'like_count': row.like_count or 0,
            'is_liked': bool(row.is_liked),
            'nickname': row.nickname,
            'avatar': row.avatar or '/static/avatars/default.jpg',
            'user_id': row.user_id,
            'replies': []
        }
        comment_map[row.comment_id] = comment

    # 第二遍：遍历所有评论，把子评论挂到父节点的 replies 里
    for comment in comment_map.values():
        if comment['parent_id'] == 0:
            root_comments.append(comment)
        elif comment['parent_id'] in comment_map:
            comment_map[comment['parent_id']]['replies'].append(comment)
        # else: 父评论被删了，理论上不会出现，但保险起见也挂到根

    return jsonify(code=200, data=root_comments)

# ====================== 举报功能 ======================
@app.route('/api/report/submit', methods=['POST'])
def api_report_submit():
    try:
        if 'user_id' not in session:
            return jsonify(code=401, msg='请先登录')

        data = request.get_json()
        if not data:
            return jsonify(code=400, msg='请求数据为空')

        target_type = data.get('target_type')
        target_id = data.get('target_id')
        reason = data.get('reason')
        description = data.get('description', '')

        if target_type not in ['goods', 'user']:
            return jsonify(code=400, msg='举报类型错误')
        if not target_id or not reason:
            return jsonify(code=400, msg='参数不完整')

        try:
            target_id = int(target_id)
        except:
            return jsonify(code=400, msg='ID格式错误')

        # 防刷
        one_hour_ago = datetime.datetime.now() - datetime.timedelta(minutes=30)
        count = db.session.execute(
            db.text("SELECT COUNT(*) FROM report WHERE reporter_id = :uid AND target_type = :type AND target_id = :tid AND created_at > :time"),
            {'uid': session['user_id'], 'type': target_type, 'tid': target_id, 'time': one_hour_ago}
        ).scalar()

        if count > 0:
            return jsonify(code=403, msg='您已举报过该内容，请勿重复提交')

        # 明确指定列插入，避免字段缺失报错
        db.session.execute(
            db.text("""
                INSERT INTO report 
                (reporter_id, target_type, target_id, reason, description, evidence, status)
                VALUES (:reporter, :type, :tid, :reason, :desc, '', 0)
            """),
            {
                'reporter': session['user_id'],
                'type': target_type,
                'tid': target_id,
                'reason': reason,
                'desc': description
            }
        )
        db.session.commit()

        return jsonify(code=200, msg='举报已提交，感谢您的反馈！我们会尽快处理')

    except Exception as e:
        print("举报接口详细错误:", str(e))  # 控制台会打印具体错因
        db.session.rollback()
        return jsonify(code=500, msg='服务器错误，请稍后重试')
    
    # ====================== 消息中心工具函数 ======================
SYSTEM_USER_ID = 0  # 定义系统发送者ID为0

def send_message(to_user_id, content, from_user_id=SYSTEM_USER_ID, order_id=None):
    """统一发送消息（系统消息 from_user_id=0，聊天消息填真实ID）"""
    try:
        msg = Message(
            to_user_id=to_user_id,
            from_user_id=from_user_id,
            order_id=order_id,
            content=content
        )
        db.session.add(msg)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print("【发送消息失败】", str(e))
        return False
    

@app.route('/api/message/list')
@login_required
def api_message_list():
    uid = session['user_id']

    # 修改：移除 type = 'chat' 限制，显示所有消息（系统 + 聊天）
    sql = """
        SELECT 
            latest.*,
            u.user_id AS opponent_id,
            u.nickname AS opponent_nick,
            u.avatar AS opponent_avatar,
            COUNT(unread.msg_id) AS unread_count
        FROM (
            SELECT m.*,
                   ROW_NUMBER() OVER (PARTITION BY 
                     CASE WHEN from_user_id = 0 THEN m.msg_id ELSE  -- 系统消息单独分组
                       CASE WHEN from_user_id = :uid THEN to_user_id ELSE from_user_id END
                     END
                     ORDER BY created_at DESC) as rn
            FROM message m
            WHERE (m.to_user_id = :uid)  -- 只看发给我的消息（包括系统消息）
        ) latest
        LEFT JOIN user u ON u.user_id = CASE WHEN latest.from_user_id = :uid THEN latest.to_user_id ELSE latest.from_user_id END
            AND latest.from_user_id != 0  -- 系统消息不join用户
        LEFT JOIN message unread ON unread.to_user_id = :uid 
               AND ((unread.from_user_id = u.user_id AND u.user_id IS NOT NULL) OR unread.from_user_id = 0)
               AND unread.is_read = 0
        WHERE latest.rn = 1
        GROUP BY latest.msg_id, u.user_id, u.nickname, u.avatar
        ORDER BY latest.created_at DESC
    """
    rows = db.session.execute(db.text(sql), {'uid': uid}).fetchall()

    conversations = []
    for r in rows:
        # 系统消息特殊处理
        if r.from_user_id == 0:
            conv = {
                'opponent_id': 0,
                'opponent_nick': '系统通知',
                'opponent_avatar': '/static/avatars/system.jpg',  # 可放一个系统图标
                'last_message': r.content,
                'last_time': r.created_at.strftime('%m-%d %H:%M'),
                'unread_count': r.unread_count or 0
            }
        else:
            conv = {
                'opponent_id': r.opponent_id,
                'opponent_nick': r.opponent_nick or '未知用户',
                'opponent_avatar': r.opponent_avatar or '/static/avatars/default.jpg',
                'last_message': r.content,
                'last_time': r.created_at.strftime('%m-%d %H:%M'),
                'unread_count': r.unread_count or 0
            }
        conversations.append(conv)

    return jsonify(code=200, data=conversations)

@app.route('/api/message/unread_count')
@login_required
def api_message_unread_count():
    uid = session['user_id']
    count = db.session.execute(db.text("""
        SELECT COUNT(*) FROM message 
        WHERE to_user_id = :uid AND is_read = 0
    """), {'uid': uid}).scalar()
    return jsonify(code=200, count=count or 0)

@app.route('/api/message/mark_read', methods=['POST'])
@login_required
def api_message_mark_read():
    data = request.get_json() or {}
    order_id = data.get('order_id')  # 可选：只标记某个订单的消息
    msg_ids = data.get('msg_ids', [])  # 可选：标记指定消息

    sql = "UPDATE message SET is_read = 1 WHERE to_user_id = :uid AND is_read = 0"
    params = {'uid': session['user_id']}

    if order_id:
        sql += " AND order_id = :order_id"
        params['order_id'] = order_id
    elif msg_ids:
        sql += " AND msg_id IN :msg_ids"
        params['msg_ids'] = tuple(msg_ids)

    db.session.execute(db.text(sql), params)
    db.session.commit()
    return jsonify(code=200, msg='已标记已读')

@app.route('/messages')
@login_required
def messages():
    user = User.query.get(session['user_id'])
    to_user_id = request.args.get('to', type=int)
    to_user = User.query.get(to_user_id) if to_user_id else None
    return render_template('visiter/my_messages.html', user=user, to_user=to_user)

@app.route('/api/message/send', methods=['POST'])
@login_required
def api_message_send():
    data = request.get_json() or {}
    to_user_id = data.get('to_user_id')
    content = data.get('content', '').strip()
    order_id = data.get('order_id')  # 可选
    goods_id = data.get('goods_id')  # 可选

    if not to_user_id or not content:
        return jsonify(code=400, msg='参数不完整')
    if int(to_user_id) == session['user_id']:
        return jsonify(code=400, msg='不能给自己发消息')

    sender = User.query.get(session['user_id'])

    try:
        msg = Message(
            from_user_id=session['user_id'],
            from_nickname=sender.nickname,
            to_user_id=to_user_id,
            order_id=order_id,
            goods_id=goods_id,
            type='chat',
            content=content
        )
        db.session.add(msg)
        db.session.commit()

        msg_data = {
            'msg_id': msg.msg_id,
            'from_user_id': session['user_id'],
            'from_nickname': sender.nickname,
            'from_avatar': sender.avatar or '/static/avatars/default.jpg',
            'content': content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_me': True
        }
        return jsonify(code=200, data=msg_data)

    except Exception as e:
        db.session.rollback()
        print("发送失败:", str(e))
        return jsonify(code=500, msg='发送失败')
    
@app.route('/api/message/chat')
@login_required
def api_message_chat():
    to_user_id = request.args.get('to_user_id', type=int)
    if not to_user_id:
        return jsonify(code=400, msg='缺少对方ID')

    if to_user_id == session['user_id']:
        return jsonify(code=400, msg='参数错误')

    # 查询两人之间所有聊天消息（双向）
    rows = db.session.execute(db.text("""
        SELECT m.*, u.nickname AS from_nickname_temp, u.avatar AS from_avatar
        FROM message m
        LEFT JOIN user u ON m.from_user_id = u.user_id
        WHERE m.type = 'chat'
          AND (
            (m.from_user_id = :me AND m.to_user_id = :you)
            OR
            (m.from_user_id = :you AND m.to_user_id = :me)
          )
        ORDER BY m.created_at DESC
        LIMIT 50
    """), {'me': session['user_id'], 'you': to_user_id}).fetchall()

    messages = []
    for row in reversed(rows):  # 倒序变正序（最早的在前面）
        msg = dict(row._mapping)
        msg['created_at'] = row.created_at.strftime('%Y-%m-%d %H:%M')
        msg['from_nickname'] = row.from_nickname_temp or row.from_nickname or '未知用户'
        msg['from_avatar'] = row.from_avatar or '/static/avatars/default.jpg'
        msg['is_me'] = (row.from_user_id == session['user_id'])
        messages.append(msg)

    # 标记为已读（只标记对方发给我的消息）
    db.session.execute(db.text("""
        UPDATE message 
        SET is_read = 1 
        WHERE to_user_id = :me AND from_user_id = :you AND is_read = 0 AND type = 'chat'
    """), {'me': session['user_id'], 'you': to_user_id})
    db.session.commit()

    return jsonify(code=200, data=messages)

@app.route('/chat/<int:order_id>')
@login_required
def order_chat(order_id):
    order = db.session.execute(db.text("""
        SELECT o.*, g.title, buyer.nickname AS buyer_nick, seller.nickname AS seller_nick,
               buyer.avatar AS buyer_avatar, seller.avatar AS seller_avatar
        FROM `order` o
        JOIN goods g ON o.goods_id = g.goods_id
        JOIN user buyer ON o.buyer_id = buyer.user_id
        JOIN user seller ON o.seller_id = seller.user_id
        WHERE o.order_id = :oid AND (o.buyer_id = :uid OR o.seller_id = :uid)
    """), {'oid': order_id, 'uid': session['user_id']}).fetchone()

    if not order:
        return "订单不存在或无权访问", 404

    # 对方用户
    opponent = {
        'user_id': order.seller_id if order.buyer_id == session['user_id'] else order.buyer_id,
        'nickname': order.seller_nick if order.buyer_id == session['user_id'] else order.buyer_nick,
        'avatar': order.seller_avatar if order.buyer_id == session['user_id'] else order.buyer_avatar,
        'college': ''  # 可后续加
    }

    return render_template('visiter/my_messages.html', 
                       user=User.query.get(session['user_id']), 
                       order=order, 
                       opponent=opponent,
                       is_order_chat=True)  # ← 新增标志


# ====================== 管理员相关装饰器 ======================
def admin_required(f):
    """管理员权限装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or not session.get('is_admin'):
            session.clear()  # 可选：强制清除session，防止残留
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ====================== 管理员登录 ======================
@app.route('/admin')
def admin_login():
    return render_template('admin/admin_login.html')

@app.route('/admin/login', methods=['POST'])
def admin_login_post():
    data = request.get_json()
    account = data.get('account')
    password = data.get('password')

    user = User.query.filter_by(account=account, is_admin=1).first()
    if user and check_password_hash(user.password, password):
        session.clear()  # ← 关键：完全清除旧 session（包括残留的 is_admin）
        session['user_id'] = user.user_id
        session['is_admin'] = True
        session['nickname'] = user.nickname

        # 可选：清除可能残留的普通用户字段（防万一）
        session.pop('some_other_key', None)
        return jsonify(code=200, msg='登录成功')
    return jsonify(code=400, msg='账号或密码错误，或非管理员身份')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin')

# ====================== 后台首页 - 数据统计看板 ======================
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # 统计数据
    stats = {}

    # 总GMV（已支付订单金额总和）
    total_gmv = db.session.execute(db.text("""
        SELECT COALESCE(SUM(total_amount), 0) FROM `order` WHERE pay_status = 1
    """)).scalar()

    # 今日交易额
    today_gmv = db.session.execute(db.text("""
        SELECT COALESCE(SUM(total_amount), 0) FROM `order` 
        WHERE pay_status = 1 AND DATE(pay_time) = CURDATE()
    """)).scalar()

    # 总订单数 / 今日订单数
    total_orders = db.session.execute(db.text("SELECT COUNT(*) FROM `order`")).scalar()
    today_orders = db.session.execute(db.text("""
        SELECT COUNT(*) FROM `order` WHERE DATE(created_at) = CURDATE()
    """)).scalar()

    # 总用户数 / 今日注册
    total_users = User.query.count()
    today_reg = User.query.filter(db.func.DATE(User.reg_time) == datetime.date.today()).count()

    # 毕业生清仓商品数
    batch_goods = goods.query.filter(goods.is_batch == 1, goods.status == 1).count()

    # 待处理举报数
    pending_reports = db.session.execute(db.text("""
        SELECT COUNT(*) FROM report WHERE status = 0
    """)).scalar()

    stats = {
        'total_gmv': float(total_gmv),
        'today_gmv': float(today_gmv),
        'total_orders': total_orders,
        'today_orders': today_orders,
        'total_users': total_users,
        'today_reg': today_reg,
        'batch_goods': batch_goods,
        'pending_reports': pending_reports,
    }

    return render_template('admin/admin_dashboard.html', stats=stats)

# ====================== 商品管理 ======================
@app.route('/admin/goods')
@admin_required
def admin_goods():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    keyword = request.args.get('keyword', '').strip()

    # 基础查询：只取 goods 表字段 + 卖家昵称
    base_query = db.session.query(
        goods.goods_id,
        goods.title,
        goods.price,
        goods.status,
        goods.on_shelf_time,
        User.nickname.label('seller_nick')
    ).outerjoin(User, goods.user_id == User.user_id)

    if keyword:
        base_query = base_query.filter(goods.title.ilike(f'%{keyword}%'))

    # 分页
    pagination = base_query.order_by(goods.goods_id.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    # 手动构造列表，每项是一个字典（模板更易用）
    goods_list = []
    for row in pagination.items:
        goods_list.append({
            'goods_id': row.goods_id,
            'title': row.title,
            'price': float(row.price),
            'status': row.status,
            'on_shelf_time': row.on_shelf_time,
            'seller_nick': row.seller_nick or '未知用户'
        })

    return render_template(
        'admin/admin_goods.html',
        goods=goods_list,          # ← 明确传 goods 列表
        pagination=pagination,
        keyword=keyword
    )

@app.route('/admin/goods/action', methods=['POST'])
@admin_required
def admin_goods_action():
    data = request.get_json()
    goods_id = data.get('goods_id')
    action = data.get('action')  # 'offshelf' 或 'delete'

    if not goods_id or action not in ['offshelf', 'delete']:
        return jsonify(code=400, msg='参数错误')

    target_goods = goods.query.get_or_404(goods_id)

    try:
        if action == 'offshelf':
            target_goods.status = 0  # 下架
            db.session.commit()
            return jsonify(code=200, msg='商品已下架')

        elif action == 'delete':
            # 删除关联图片记录（可选，防止垃圾数据）
            db.session.execute(db.text("DELETE FROM goods_image WHERE goods_id = :gid"), {'gid': goods_id})
            db.session.delete(target_goods)
            db.session.commit()
            return jsonify(code=200, msg='商品已删除')

    except Exception as e:
        db.session.rollback()
        print("【管理员操作商品失败】", str(e))
        return jsonify(code=500, msg='操作失败，请重试')

    return jsonify(code=400, msg='未知操作')

# ====================== 用户管理 ======================
@app.route('/admin/users')
@admin_required
def admin_users():
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()

    query = User.query
    if keyword:
        query = query.filter(
            db.or_(User.account.ilike(f'%{keyword}%'), User.nickname.ilike(f'%{keyword}%'))
        )

    pagination = query.order_by(User.user_id.desc())\
        .paginate(page=request.args.get('page', 1, type=int), per_page=20, error_out=False)

    return render_template('admin/admin_users.html', users=pagination.items, pagination=pagination, keyword=keyword)

@app.route('/admin/user/ban', methods=['POST'])
@admin_required
def admin_user_ban():
    data = request.get_json()
    user_id = data['user_id']
    ban = data['ban']  # True=封禁 False=解封

    user = User.query.get_or_404(user_id)
    user.status = 0 if ban else 1
    db.session.commit()
    return jsonify(code=200, msg='操作成功')

# ====================== 分类管理 ======================
@app.route('/admin/categories')
@admin_required
def admin_categories():
    categories = Category.query.order_by(Category.sort).all()
    return render_template('admin/admin_categories.html', categories=categories)

@app.route('/admin/category', methods=['POST'])
@admin_required
def admin_category_action():
    data = request.get_json()
    action = data['action']
    if action == 'add':
        cat = Category(name=data['name'], sort=data.get('sort', 0), enabled=1)
        db.session.add(cat)
    elif action == 'edit':
        cat = Category.query.get(data['cate_id'])
        cat.name = data['name']
        cat.sort = data['sort']
        cat.enabled = data['enabled']
    elif action == 'delete':
        cat = Category.query.get(data['cate_id'])
        db.session.delete(cat)
    db.session.commit()
    return jsonify(code=200, msg='操作成功')

# ====================== 举报管理 ======================
@app.route('/admin/reports')
@admin_required
def admin_reports():
    page = request.args.get('page', 1, type=int)
    pagination = db.session.query(Report).order_by(Report.created_at.desc())\
        .paginate(page=page, per_page=15, error_out=False)
    return render_template('admin/admin_reports.html', reports=pagination.items, pagination=pagination)

@app.route('/admin/report/handle', methods=['POST'])
@admin_required
def admin_report_handle():
    data = request.get_json()
    report_id = data.get('report_id')
    status = data.get('status')  # 1=已处理 2=已忽略
    auto_off_goods = data.get('auto_off_goods', False)

    if not report_id or status not in [1, 2]:
        return jsonify(code=400, msg='参数错误')

    report = Report.query.get_or_404(report_id)

    # 更新举报状态
    report.status = status
    db.session.commit()

    # 自动下架商品
    if status == 1 and auto_off_goods and report.target_type == 'goods':
        target_goods = goods.query.get(report.target_id)
        if target_goods:
            target_goods.status = 0
            db.session.commit()
            print(f"【商品下架成功】goods_id={report.target_id}")

    # ========== 关键修复：发送系统通知消息 ==========
    try:
        target_desc = '商品' if report.target_type == 'goods' else '用户'
        if status == 1:
            msg_content = f"您举报的{target_desc}（ID: {report.target_id}）已处理，感谢您的反馈！"
            if auto_off_goods and report.target_type == 'goods':
                msg_content += " 该商品已被下架。"
        else:
            msg_content = f"您举报的{target_desc}（ID: {report.target_id}）经审核未发现问题，已忽略。感谢您的关注！"

        notification = Message(
            from_user_id=45,   # ← 关键：改成45
            from_nickname='系统通知',
            to_user_id=report.reporter_id,
            type='system',
            content=msg_content,
            is_read=0
        )
        db.session.add(notification)
        db.session.commit()
        print(f"【举报通知发送成功】发送给用户 {report.reporter_id}: {msg_content}")

    except Exception as e:
        db.session.rollback()
        print("【举报通知发送失败】", str(e))

    return jsonify(code=200, msg='处理完成，已通知举报人')

@app.route('/admin/stats/gmv')
@admin_required
def admin_stats_gmv():
    # 分类销售额
    cate_sales = db.session.execute(db.text("""
        SELECT c.name, COALESCE(SUM(o.total_amount), 0) as sales
        FROM category c
        LEFT JOIN goods g ON g.cate_id = c.cate_id
        LEFT JOIN `order` o ON o.goods_id = g.goods_id AND o.pay_status = 1
        GROUP BY c.cate_id
        ORDER BY sales DESC
    """)).fetchall()

    # 每日交易额（最近30天）
    daily_sales = db.session.execute(db.text("""
        SELECT DATE(pay_time) as date, COALESCE(SUM(total_amount), 0) as amount
        FROM `order`
        WHERE pay_status = 1 AND pay_time >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY date
        ORDER BY date
    """)).fetchall()

    return render_template('admin/admin_stats_gmv.html', cate_sales=cate_sales, daily_sales=daily_sales)


@app.route('/admin/stats/today_gmv')
@admin_required
def admin_stats_today_gmv():
    hourly_sales = db.session.execute(db.text("""
        SELECT 
            HOUR(pay_time) AS hour,
            COALESCE(SUM(total_amount), 0) AS amount
        FROM `order`
        WHERE pay_status = 1 
          AND DATE(pay_time) = CURDATE()
        GROUP BY hour
        ORDER BY hour
    """)).fetchall()

    hours = [f"{i:02d}:00" for i in range(24)]
    amounts = [0.0] * 24
    for row in hourly_sales:
        amounts[row.hour] = float(row.amount)

    total_today = sum(amounts)
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    return render_template('admin/admin_stats_today_gmv.html', 
                           hours=hours, 
                           amounts=amounts, 
                           total_today=total_today,
                           current_time=current_time)
@app.route('/admin/stats/orders')
@admin_required
def admin_stats_orders():
    # 订单状态分布
    status_data = db.session.execute(db.text("""
        SELECT 
            pay_status,
            COUNT(*) AS count,
            COALESCE(SUM(total_amount), 0) AS amount
        FROM `order`
        GROUP BY pay_status
        ORDER BY pay_status
    """)).fetchall()

    # 状态映射
    status_map = {0: '待支付', 1: '已支付', 2: '已完成'}
    labels = []
    counts = []
    amounts = []
    colors = ['#e74c3c', '#f39c12', '#27ae60']  # 红橙绿

    total_orders = 0
    for row in status_data:
        status_name = status_map.get(row.pay_status, '未知')
        labels.append(status_name)
        counts.append(row.count)
        amounts.append(float(row.amount))
        total_orders += row.count

    return render_template('admin/admin_stats_orders.html',
                           labels=labels,
                           counts=counts,
                           amounts=amounts,
                           colors=colors,
                           total_orders=total_orders)

# ====================== 订单管理 ======================
@app.route('/admin/orders')
@admin_required
def admin_orders():
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    per_page = 20

    # 正确定义卖家别名
    seller = db.aliased(User, name='seller')

    # 查询订单列表，联表获取商品标题、买家信息、卖家信息
    base_query = db.session.query(
        Order.order_no,
        Order.goods_id,
        Order.total_amount,
        Order.quantity,
        Order.pay_status,
        Order.created_at,
        goods.title,
        User.nickname.label('buyer_nick'),
        User.avatar.label('buyer_avatar'),
        seller.nickname.label('seller_nick'),
        seller.avatar.label('seller_avatar')
    ).join(goods, goods.goods_id == Order.goods_id) \
     .join(User, User.user_id == Order.buyer_id) \
     .join(seller, seller.user_id == Order.seller_id)  # 这里用 join 而不是 outerjoin，因为卖家一定存在

    if keyword:
        base_query = base_query.filter(
            or_(
                Order.order_no.ilike(f'%{keyword}%'),
                goods.title.ilike(f'%{keyword}%')
            )
        )

    pagination = base_query.order_by(Order.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    # 转换为字典列表，方便模板使用 {{ o.order_no }} 语法
    orders = [row._asdict() for row in pagination.items]

    return render_template('admin/admin_orders.html',
                           orders=orders,
                           pagination=pagination,
                           keyword=keyword)

# ====================== 今日订单管理 ======================
@app.route('/admin/orders/today')
@admin_required
def admin_orders_today():
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    per_page = 20

    # 正确定义卖家别名
    seller = db.aliased(User, name='seller')

    # 今天的时间范围：从今天00:00:00 到现在
    today_start = datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.datetime.now()

    # 查询今日订单
    base_query = db.session.query(
        Order.order_no,
        Order.goods_id,
        Order.total_amount,
        Order.quantity,
        Order.pay_status,
        Order.created_at,
        goods.title,
        User.nickname.label('buyer_nick'),
        User.avatar.label('buyer_avatar'),
        seller.nickname.label('seller_nick'),
        seller.avatar.label('seller_avatar')
    ).join(goods, goods.goods_id == Order.goods_id) \
     .join(User, User.user_id == Order.buyer_id) \
     .join(seller, seller.user_id == Order.seller_id) \
     .filter(Order.created_at >= today_start) \
     .filter(Order.created_at <= today_end)

    if keyword:
        base_query = base_query.filter(
            or_(
                Order.order_no.ilike(f'%{keyword}%'),
                goods.title.ilike(f'%{keyword}%')
            )
        )

    pagination = base_query.order_by(Order.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    orders = [row._asdict() for row in pagination.items]

    return render_template('admin/admin_orders_today.html',
                           orders=orders,
                           pagination=pagination,
                           keyword=keyword,
                           today_date=today_start.strftime('%Y年%m月%d日'))  # 传递今天日期用于标题显示

# ====================== 今日注册用户 ======================
@app.route('/admin/users/today')
@admin_required
def admin_users_today():
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()  # ← 这里修复了
    per_page = 20

    # 今天的时间范围：从今天00:00:00 开始
    today_start = datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    # 查询今日注册用户
    query = User.query.filter(User.reg_time >= today_start) \
                      .order_by(User.reg_time.desc())

    if keyword:
        query = query.filter(
            db.or_(
                User.nickname.ilike(f'%{keyword}%'),
                User.account.ilike(f'%{keyword}%'),
                User.stu_id.ilike(f'%{keyword}%'),
                User.email.ilike(f'%{keyword}%')
            )
        )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    return render_template('admin/admin_users_today.html',
                           users=users,
                           pagination=pagination,
                           keyword=keyword,
                           today_date=today_start.strftime('%Y年%m月%d日'))

# ====================== 毕业生清仓商品管理 ======================
@app.route('/admin/batch_goods')
@admin_required
def admin_batch_goods():
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    per_page = 20

    # 查询毕业生清仓商品（is_batch=1）
    query = goods.query.filter(goods.is_batch == 1) \
                       .order_by(goods.on_shelf_time.desc())

    if keyword:
        query = query.filter(
            db.or_(
                goods.title.ilike(f'%{keyword}%'),
                goods.description.ilike(f'%{keyword}%')
            )
        )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items

    # 额外联表获取发布者信息（可选，方便显示卖家）
    batch_goods = []
    for g in items:
        item = g.__dict__
        seller = User.query.get(g.user_id)
        item['seller_nickname'] = seller.nickname if seller else '未知用户'
        item['seller_avatar'] = seller.avatar or '/static/avatars/default.jpg' if seller else '/static/avatars/default.jpg'
        batch_goods.append(item)

    return render_template('admin/admin_batch_goods.html',
                           goods=batch_goods,
                           pagination=pagination,
                           keyword=keyword)

# ====================== 自定义 Jinja2 过滤器 ======================
@app.template_filter('strftime')
def _jinja2_filter_strftime(date, fmt=None):
    """
    自定义 strftime 过滤器
    用法：{{ some_date | strftime('%Y-%m-%d %H:%M') }}
    如果日期为 None，返回 '未知'
    """
    if date is None:
        return '未知'
    
    if isinstance(date, str):
        # 如果是字符串，先尝试解析（可选）
        try:
            date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        except:
            return date  # 解析失败原样返回
    
    if fmt is None:
        fmt = '%Y-%m-%d %H:%M'
    
    return date.strftime(fmt)
# ====================== 管理员专用查看（绕过权限限制） ======================

@app.route('/admin/goods/view/<int:goods_id>')
@admin_required
def admin_goods_view(goods_id):
    g = goods.query.get_or_404(goods_id)
    images = goods_image.query.filter_by(goods_id=goods_id).order_by(goods_image.sort).all()
    seller = User.query.get(g.user_id)
    
    # 直接复用前端 goods_detail.html 模板
    return render_template('visiter/goods_detail.html', 
                           goods=g, 
                           images=images, 
                           user=session.get('user') or {},  # 防止未登录报错
                           seller=seller)  # 如果模板需要 seller，可加

@app.route('/admin/order/view/<order_no>')
@admin_required
def admin_order_view(order_no):
    order = Order.query.filter_by(order_no=order_no).first_or_404()
    
    # 获取商品封面（从 goods_image 取第一张，或用默认）
    cover = goods_image.query.filter_by(goods_id=order.goods_id).first()
    cover_img = cover.url if cover else '/static/avatars/goodspictures/default.jpg'
    
    # 买家/卖家昵称（模板中用到）
    buyer = User.query.get(order.buyer_id)
    seller = User.query.get(order.seller_id)
    
    # 构造模板需要的字段（模拟前端传参）
    order_data = {
        'order_no': order.order_no,
        'pay_status': order.pay_status,
        'created_at': order.created_at,
        'pay_time': order.pay_time,
        'confirm_time': order.confirm_time,
        'total_amount': order.total_amount,
        'quantity': order.quantity,
        'title': goods.query.get(order.goods_id).title,  # 商品标题
        'cover_img': cover_img,
        'buyer_nick': buyer.nickname if buyer else '未知',
        'seller_nick': seller.nickname if seller else '未知',
        'buyer_id': order.buyer_id,
        'seller_id': order.seller_id,
    }
    
    # 管理员查看时，伪装成“本人”以避免模板逻辑报错（可选）
    fake_user = {'user_id': None}  # 或 seller_id，随便选一个让按钮显示正常
    
    return render_template('visiter/order_detail.html', 
                           order=order_data, 
                           user=fake_user)  # 关键：传入 user 避免模板报错
with app.app_context():
    db.create_all()  # 首次运行时自动创建所有表（开发环境非常方便
# ====================== 程序启动入口 ======================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False 上线时关闭
