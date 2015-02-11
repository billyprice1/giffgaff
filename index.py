# -*- coding: utf-8 -*-
from flask import Flask, g, request, render_template, session
from captcha.image import ImageCaptcha
import sqlite3, re, time, urllib2, json, random, sys
sys.path.insert(0, './mail')
from mail import send_email


app = Flask(__name__)
app.debug = True
app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
##################
# 一些全局配置变量
##################
DATABASE = "tmp/data.sqlite"
ADMIN = "admin"
PASSWORD = "admin"
EMAIL_PATTERN = '^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$'
PHONE_PATTERN = '(1)(3\d|4[5,7]|5[0-3,5-9]|8[0,2,3,6-9])\D*(\d{4})\D*(\d{4})$'

##################
# 这里放一些辅助函数
##################

def connect_db():
    return sqlite3.connect(DATABASE)

def init_db():
    db = connect_db()
    with open('schema.sql') as f:
        db.cursor().executescript(f.read())
    db.commit()

def valid_form(form):
    '''
    接收一个request.formd对象，检查各个field，返回错误字符串
    若验证成功，则返回空字符串
    '''
    errors = []

    # 邮箱验证
    email = form['email']
    if not email:
        errors.append(u"邮箱不能为空")
    elif not re.match(EMAIL_PATTERN, email):
        errors.append(u"请输入正确的邮箱")
    else:
        try:
            conn = connect_db()
            cur = conn.cursor()
            cur.execute("select email from entries where email='%s'" % email)
            data = cur.fetchall()
            if len(data) > 0:
                errors.append(u"该邮箱已经申请过，请勿重复提交")
            cur.close()
        except Exception as e:
            errors.append(str(e))
        finally:
            conn.close()

    # 姓名验证
    name = form['name']
    if not name:
        errors.append(u"姓名不能为空")

    # 电话验证
    phone = form['phone']
    if not phone:
        errors.append(u"电话不能为空")
    elif not re.match(PHONE_PATTERN, phone):
        errors.append(u"请输入正确的电话，11位国内号码")

    # 卡数验证
    nano_qty = int(form['nano_qty'])
    micro_qty = int(form['micro_qty'])
    if not nano_qty and not micro_qty:
        errors.append(u"至少选择一张卡")

    if not errors:
        # 检查验证码
        if session['captcha'] != form['captcha']:
            errors.append(u"验证码输入错误")

    return errors

def save_record(form):
    '''
    将验证成功的记录保存到sqlite中
    若数据库操作过程发生异常，捕获后将错误信息添加到errors中进行返回
    '''
    errors = []
    try:
        conn = connect_db()
        conn.execute("insert into entries (email, name, phone, nano_qty, micro_qty) values (?, ?, ?, ?, ?)", (form['email'], form['name'], form['phone'], form['nano_qty'], form['micro_qty']))
        conn.commit()
    except Exception as e:
        errors.append(str(e))
    finally:
        conn.close()
        return errors

def get_all_entries():
    try:
        # 获取所有条目
        errors = []
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("select * from entries")
        results = cur.fetchall()
        cur.close()

        # 计算统计信息
        stats = {}
        stats['count'] = len(results)
        stats['nano_total'] = sum([row[4] for row in results])
        stats['micro_total'] = sum([row[5] for row in results])
        print stats
    except Exception as e:
        errors.append(str(e))
    finally:
        conn.close()
        return (results, stats, errors)

def generate_captcha():
    '''
    验证码生成函数。调用后讲生成一个4位数字的随机字符串captcha_str
    根据该字符串生成图片，存放在/static/captcha.png
    并设置session['captcha'] = captcha_str
    '''
    # 生成验证码
    captch_str = "".join([str(random.choice(range(0,10))) for i in range(4)])
    session['captcha'] = captch_str
    image = ImageCaptcha(width=118, height=38, font_sizes=(37,37,37))
    image.write(captch_str, "static/captcha.png")

@app.template_filter('randSuffix')
def reverse_filter(original_url):
    '''
    为验证码图片请求地址末尾加上随机字符串，确保图片不会被缓存，每次都会请求最新图片
    '''
    suffix = str(int(time.time()*100))
    return original_url + "?" + suffix

##################
# 下面均为视图处理函数
##################
# 首页
@app.route('/')
@app.route('/index', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        # 验证码生成
        generate_captcha()
        return render_template("index.html")

    elif request.method == 'POST':
        # 先做表单验证，再重新生成验证码，避免session['captcha']被覆盖
        errors = valid_form(request.form)
        generate_captcha()
        if not errors:
            # 表单验证成功，保存数据
            errors = save_record(request.form)
            if not errors:
                # 发送确认邮件
                receiver_list = [(request.form['email'], request.form['name'])]
                subject = 'giffgaff 订单确认'
                text = "您的 giffgaff 订单已经确认！请等待我们的后续通知。\n预期将于5月底通知具体的领卡时间和地点。\n"
                send_email(receiver_list, subject, text)
                return render_template("index.html", ok_flag=True)
            else:
                return render_template("index.html", errors=errors)
        else:
            # 表单验证失败，返回带错误信息的模版
            return render_template("index.html", errors=errors)

# 后台页面
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'GET':
        if session.has_key("admin_flag"):
            results, stats, errors = get_all_entries()
            return render_template("admin.html", results=results, stats=stats, errors=errors)
        else:
            return render_template("admin.html")

    elif request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == ADMIN and password == PASSWORD:
            # 输入正确，设置session，下次直接进入后台
            if not session.has_key("admin_flag"):
                session['admin_flag'] = True

            results, stats, errors = get_all_entries()

            return render_template("admin.html", results=results, stats=stats, errors=errors)
        else:
            # 登陆验证失败
            return render_template("admin.html", errors = [u"输入错误"])

# 后台json api
@app.route('/admin/json', methods=['POST'])
def adminJson():
    username = request.form['username']
    password = request.form['password']

    if username == ADMIN and password == PASSWORD:
        # 验证成功，获取所有数据
        results = get_all_entries()[0]
        return json.dumps(results)

# 查询页面
@app.route('/enquiry')
def enquiry():
    enquiry_email = request.args.get('email')
    delete = request.args.get('delete')
    print delete
    if not enquiry_email:
        # 给出初始查询页面提示
        return render_template("enquiry.html")
    elif not delete:
        # 尝试查询
        result = []
        errors = []
        try:
            conn = connect_db()
            cur = conn.cursor()
            cur.execute("select * from entries where email='%s'" % enquiry_email)
            data = cur.fetchall()
            if len(data) > 0:
                result = data[0]
            cur.close()
        except Exception as e:
            errors.append(str(e))
        finally:
            conn.close()
            if len(result) > 0:
                # 有查询结果
                return render_template("enquiry.html", result=result, errors=errors)
            else:
                # 无查询结果
                return render_template("enquiry.html", main_msg=u"查询不到该邮箱的预定信息！", msg_type="error", errors=errors)

    elif delete:
        # 进行删除
        errors = []
        try:
            conn = connect_db()
            cur = conn.cursor()
            cur.execute("delete from entries where email='%s'" % enquiry_email)
            cur.close()
        except Exception as e:
            errors.append(str(e))
        finally:
            conn.commit()
            conn.close()
            if cur.rowcount > 0:
                # 删除成功
                return render_template("enquiry.html", main_msg=u"预定信息删除成功！", msg_type="success", errors=errors)
                pass
            else:
                # 没有数据被影响
                return render_template("enquiry.html", main_msg=u"无法删除不存在的信息！", msg_type="error", errors=errors)


        return "Going to delete"

# 激活页面
@app.route('/activate')
def activate():
    return render_template("activate.html")

# 关于页面
@app.route('/about')
def about():
    return render_template("about.html")

# 404错误页面
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

if __name__ == "__main__":
    # 本地测试环境
    app.run()
else:
    # BAE发布环境
    from bae.core.wsgi import WSGIApplication
    application = WSGIApplication(app)
