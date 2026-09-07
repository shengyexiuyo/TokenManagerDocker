#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Token Manager Web Server - Flask后端服务
提供REST API与前端daisyUI界面交互

Docker版：相比原版增加以下环境变量支持，其余逻辑保持一致
- DATA_DIR：密钥等配置的保存目录（Docker中指向挂载卷，默认为程序同目录）
- PORT：服务监听端口（默认5000）
- ACCESS_CODE：访问码（设置后进入界面和所有API都需要先输入，留空则不启用）；
  多用户模式下变为注册邀请码（注册时必须输入，登录不用；留空=开放注册）
- SESSION_DAYS：登录有效期（天），默认30；0表示关闭浏览器后即需重新登录
- MULTI_USER：设为true启用多用户模式（注册/登录，每个用户独立保存自己的Token，
  第一个注册的账号自动成为管理员）
"""

import sys
import os
import hmac
import hashlib
import base64
import re
import secrets
import threading
import time

# 获取应用根目录（支持打包后的exe）
def get_app_root():
    """获取应用根目录"""
    if getattr(sys, 'frozen', False):
        # 打包后的exe
        return os.path.dirname(sys.executable)
    else:
        # 开发环境
        return os.path.dirname(os.path.abspath(__file__))

# 添加根目录到路径
sys.path.insert(0, get_app_root())

from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from typing import Optional
import json

import token_core
from token_core import (
    API_PROVIDERS,
    TokenBalanceChecker,
    add_token,
    delete_custom_config,
    delete_token,
    delete_user_data,
    get_custom_configs,
    get_pricing,
    get_provider_by_key,
    list_providers,
    list_tokens,
    migrate_legacy_user_data,
    update_token_note,
    save_custom_config
)

# 静态文件目录
STATIC_FOLDER = os.path.join(get_app_root(), 'gui')

# 配置文件保存目录：Docker中通过DATA_DIR指向挂载卷，保证容器重建后密钥不丢失
DATA_DIR = os.environ.get('DATA_DIR') or get_app_root()

# 访问码鉴权：设置环境变量ACCESS_CODE后启用；不设置则与原版一致无需登录
ACCESS_CODE = os.environ.get('ACCESS_CODE', '').strip()
AUTH_COOKIE = 'tm_auth'

# 多用户模式：MULTI_USER=true 启用注册/登录；此时ACCESS_CODE变为注册邀请码
MULTI_USER = os.environ.get('MULTI_USER', '').strip().lower() in ('1', 'true', 'yes', 'on')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SECRET_FILE = os.path.join(DATA_DIR, '.secret')


def _parse_session_days() -> float:
    """登录有效期（天）：0表示浏览器会话Cookie，关闭浏览器后需重新登录"""
    raw = os.environ.get('SESSION_DAYS', '30').strip()
    try:
        days = float(raw)
    except ValueError:
        print(f"⚠️  SESSION_DAYS 配置无效: {raw}，使用默认30天")
        return 30.0
    if days < 0:
        print(f"⚠️  SESSION_DAYS 不能为负数: {raw}，使用默认30天")
        return 30.0
    return days


SESSION_DAYS = _parse_session_days()


def _auth_mode() -> str:
    """鉴权模式：none=无需鉴权; code=访问码; multi=多用户注册登录"""
    if MULTI_USER:
        return 'multi'
    return 'code' if ACCESS_CODE else 'none'


def _auth_enabled() -> bool:
    """是否启用鉴权（任一模式）"""
    return _auth_mode() != 'none'


# ==================== 访问码模式（原有逻辑不变） ====================

def _expected_token() -> str:
    """由访问码派生的会话令牌（无状态；修改访问码后所有旧会话自动失效）"""
    return hmac.new(ACCESS_CODE.encode('utf-8'), b'token-manager-auth-v1', hashlib.sha256).hexdigest()


def _is_authenticated() -> bool:
    token = request.cookies.get(AUTH_COOKIE) or request.headers.get('X-Auth-Token')
    return bool(token) and hmac.compare_digest(token, _expected_token())


# ==================== 多用户模式：账号存储与会话 ====================

_USERNAME_RE = re.compile(r'^[A-Za-z0-9_-]{2,32}$')
_USERS_LOCK = threading.Lock()
_SECRET_LOCK = threading.Lock()
_session_secret = None


def _valid_username(username: str) -> bool:
    return bool(_USERNAME_RE.match(username or ''))


def _load_users() -> dict:
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_users(users: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USERS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(tmp, USERS_FILE)


def _pw_version(password_hash: str) -> str:
    """密码哈希的短指纹，写入会话令牌：修改密码后所有旧会话自动失效"""
    return hashlib.sha256(str(password_hash).encode('utf-8')).hexdigest()[:12]


def _get_secret() -> bytes:
    """会话签名密钥：首次使用时自动生成并持久化，容器重启后会话不失效"""
    global _session_secret
    if _session_secret:
        return _session_secret
    with _SECRET_LOCK:
        if _session_secret:
            return _session_secret
        secret = ''
        try:
            with open(SECRET_FILE, 'r', encoding='utf-8') as f:
                secret = f.read().strip()
        except Exception:
            pass
        if not secret:
            secret = secrets.token_hex(32)
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(SECRET_FILE, 'w', encoding='utf-8') as f:
                    f.write(secret)
            except Exception:
                pass
        _session_secret = secret.encode('utf-8')
        return _session_secret


def _make_session_token(username: str, password_hash: str) -> str:
    """签发会话令牌：base64(用户名|过期时间|密码指纹) + HMAC签名"""
    expires = int(time.time() + SESSION_DAYS * 86400) if SESSION_DAYS > 0 else 0
    payload = f'{username}|{expires}|{_pw_version(password_hash)}'
    b64 = base64.urlsafe_b64encode(payload.encode('utf-8')).decode('ascii').rstrip('=')
    sig = hmac.new(_get_secret(), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{b64}.{sig}'


def _parse_session_token(token: str) -> Optional[tuple]:
    """校验会话令牌，返回 (用户名, 密码指纹)；无效返回None"""
    if not token or '.' not in token:
        return None
    b64, sig = token.rsplit('.', 1)
    try:
        payload = base64.urlsafe_b64decode(b64 + '=' * (-len(b64) % 4)).decode('utf-8')
    except Exception:
        return None
    expect = hmac.new(_get_secret(), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    parts = payload.split('|')
    if len(parts) != 3:
        return None
    username, expires, pw_ver = parts
    try:
        if int(expires or 0) and int(expires) < time.time():
            return None
    except ValueError:
        return None
    return username, pw_ver


def _current_user() -> tuple:
    """multi模式下从会话解析当前用户，返回 (用户名, 用户记录) 或 (None, None)"""
    token = request.cookies.get(AUTH_COOKIE) or request.headers.get('X-Auth-Token')
    parsed = _parse_session_token(token or '')
    if not parsed:
        return None, None
    username, pw_ver = parsed
    rec = _load_users().get(username)
    if not rec or not rec.get('password_hash'):
        return None, None
    if not hmac.compare_digest(_pw_version(rec['password_hash']), pw_ver):
        return None, None
    return username, rec


def _set_session_cookie(resp, username: str, rec: dict):
    token = _make_session_token(username, rec['password_hash'])
    cookie_kwargs = dict(httponly=True, samesite='Lax')
    if SESSION_DAYS > 0:
        cookie_kwargs['max_age'] = int(SESSION_DAYS * 24 * 3600)
    # SESSION_DAYS=0 时不设max_age，即浏览器会话Cookie，关闭浏览器后需重新登录
    resp.set_cookie(AUTH_COOKIE, token, **cookie_kwargs)


def _user() -> Optional[str]:
    """当前登录用户名（multi模式，由auth_guard写入g）；其他模式返回None走全局目录"""
    return g.get('username')


# 登录/注册失败限速：同IP连续失败5次锁定15分钟（进程内计数，重启即清零）
_AUTH_FAILS = {}
_AUTH_LIMIT_LOCK = threading.Lock()
_MAX_FAILS = 5
_LOCK_SECONDS = 900


def _auth_rate_limited(ip: str) -> bool:
    with _AUTH_LIMIT_LOCK:
        rec = _AUTH_FAILS.get(ip)
        return bool(rec and rec['until'] > time.time())


def _auth_fail(ip: str):
    with _AUTH_LIMIT_LOCK:
        rec = _AUTH_FAILS.get(ip, {'count': 0, 'until': 0.0})
        rec['count'] += 1
        if rec['count'] >= _MAX_FAILS:
            rec['until'] = time.time() + _LOCK_SECONDS
            rec['count'] = 0
        _AUTH_FAILS[ip] = rec


def _auth_ok(ip: str):
    with _AUTH_LIMIT_LOCK:
        _AUTH_FAILS.pop(ip, None)


def _safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest((a or '').encode('utf-8'), (b or '').encode('utf-8'))


app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path='')
CORS(app)


@app.after_request
def no_cache_html(resp):
    # 防止浏览器缓存旧版界面，导致更新后仍显示旧功能
    if resp.mimetype == 'text/html':
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

APP_VERSION = '1.4.0'


# 配置文件路径
def get_config_path(filename: str) -> str:
    """获取配置文件路径"""
    return os.path.join(DATA_DIR, filename)


@app.before_request
def auth_guard():
    """API统一鉴权：访问码模式校验访问码会话；多用户模式解析出当前用户写入g"""
    mode = _auth_mode()
    if mode == 'none':
        return None
    path = request.path
    if path.startswith('/api/auth/') or path in ('/api/version', '/api/health'):
        return None
    if path.startswith('/api/'):
        ok = False
        if mode == 'code':
            ok = _is_authenticated()
        else:
            username, rec = _current_user()
            if username:
                ok = True
                g.username = username
                g.is_admin = bool(rec.get('is_admin'))
        if not ok:
            return jsonify({
                'success': False,
                'error': '未登录或会话已过期，请重新登录'
            }), 401
    return None


@app.route('/')
@app.route('/index.html')
def index():
    """返回主页（启用鉴权时，未登录则返回登录页）"""
    mode = _auth_mode()
    if mode == 'none':
        return send_from_directory('gui', 'index.html')
    if mode == 'code':
        if not _is_authenticated():
            return send_from_directory('gui', 'login.html')
        return send_from_directory('gui', 'index.html')
    username, _rec = _current_user()
    if not username:
        return send_from_directory('gui', 'login.html')
    return send_from_directory('gui', 'index.html')


@app.route('/api/auth/check')
def auth_check():
    """检查鉴权状态（前端据此切换登录界面、显示用户菜单/管理入口）"""
    mode = _auth_mode()
    result = {'enabled': mode != 'none', 'mode': mode, 'authenticated': False}
    if mode == 'code':
        result['authenticated'] = _is_authenticated()
    elif mode == 'multi':
        result['invite_required'] = bool(ACCESS_CODE)
        username, rec = _current_user()
        result['authenticated'] = username is not None
        if username:
            result['username'] = username
            result['is_admin'] = bool(rec.get('is_admin'))
    return jsonify(result)


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """登录：访问码模式校验访问码；多用户模式校验用户名密码"""
    mode = _auth_mode()
    if mode == 'none':
        return jsonify({'success': True, 'message': '未启用鉴权'})
    data = request.get_json(silent=True) or {}

    if mode == 'code':
        code = str(data.get('code', ''))
        if not code or not _safe_compare(code, ACCESS_CODE):
            return jsonify({'success': False, 'error': '访问码错误'}), 401
        resp = jsonify({'success': True})
        cookie_kwargs = dict(httponly=True, samesite='Lax')
        if SESSION_DAYS > 0:
            cookie_kwargs['max_age'] = int(SESSION_DAYS * 24 * 3600)
        resp.set_cookie(AUTH_COOKIE, _expected_token(), **cookie_kwargs)
        return resp

    # 多用户模式
    ip = request.remote_addr or 'unknown'
    if _auth_rate_limited(ip):
        return jsonify({'success': False, 'error': '尝试过于频繁，请15分钟后再试'}), 429
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    rec = _load_users().get(username)
    if not rec or not check_password_hash(rec.get('password_hash', ''), password):
        _auth_fail(ip)
        return jsonify({'success': False, 'error': '用户名或密码错误'}), 401
    _auth_ok(ip)
    resp = jsonify({'success': True, 'username': username, 'is_admin': bool(rec.get('is_admin'))})
    _set_session_cookie(resp, username, rec)
    return resp


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """多用户模式：注册新账号（配置了ACCESS_CODE时需邀请码；首个账号自动成为管理员）"""
    if _auth_mode() != 'multi':
        return jsonify({'success': False, 'error': '未启用多用户模式'}), 400
    ip = request.remote_addr or 'unknown'
    if _auth_rate_limited(ip):
        return jsonify({'success': False, 'error': '尝试过于频繁，请15分钟后再试'}), 429
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    invite = str(data.get('invite_code', ''))

    if not _valid_username(username):
        return jsonify({'success': False, 'error': '用户名需为2-32位字母、数字、下划线或连字符'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': '密码至少需要6位'}), 400
    if ACCESS_CODE and not _safe_compare(invite, ACCESS_CODE):
        _auth_fail(ip)
        return jsonify({'success': False, 'error': '邀请码错误'}), 401

    with _USERS_LOCK:
        users = _load_users()
        if username in users:
            return jsonify({'success': False, 'error': '该用户名已被注册'}), 400
        is_first = len(users) == 0
        rec = {
            'password_hash': generate_password_hash(password),
            'is_admin': is_first,
            'created_at': datetime.now().isoformat(),
        }
        users[username] = rec
        if is_first:
            # 单用户时代已有的密钥数据自动归入首个注册的账号
            moved = migrate_legacy_user_data(username)
            if moved:
                print(f"📦 已把原有数据迁移给首个注册用户 {username}: {', '.join(moved)}")
        _save_users(users)

    resp = jsonify({'success': True, 'username': username, 'is_admin': rec['is_admin']})
    _set_session_cookie(resp, username, rec)
    return resp


@app.route('/api/auth/change-password', methods=['POST'])
def auth_change_password():
    """多用户模式：修改自己的密码（成功后其他会话全部失效，当前会话自动续签）"""
    if _auth_mode() != 'multi':
        return jsonify({'success': False, 'error': '未启用多用户模式'}), 400
    username, rec = _current_user()
    if not username:
        return jsonify({'success': False, 'error': '未登录'}), 401
    data = request.get_json(silent=True) or {}
    old_password = str(data.get('old_password', ''))
    new_password = str(data.get('new_password', ''))
    if not check_password_hash(rec['password_hash'], old_password):
        return jsonify({'success': False, 'error': '旧密码错误'}), 401
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': '新密码至少需要6位'}), 400
    with _USERS_LOCK:
        users = _load_users()
        users[username]['password_hash'] = generate_password_hash(new_password)
        _save_users(users)
    resp = jsonify({'success': True})
    _set_session_cookie(resp, username, users[username])
    return resp


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """退出登录，清除会话Cookie"""
    resp = jsonify({'success': True})
    resp.delete_cookie(AUTH_COOKIE)
    return resp


@app.route('/api/health')
def health():
    """免鉴权探活端点（供Docker healthcheck等使用）"""
    return jsonify({'status': 'ok'})


@app.route('/api/version')
def version_route():
    """应用版本（用于确认部署的是否为新代码）"""
    return jsonify({'name': 'TokenManager', 'version': APP_VERSION})


@app.route('/api/admin/users')
def admin_list_users():
    """管理员：用户列表"""
    denied = _require_admin()
    if denied:
        return denied
    users = _load_users()
    items = [
        {'username': u, 'is_admin': bool(r.get('is_admin')), 'created_at': r.get('created_at', '')}
        for u, r in sorted(users.items())
    ]
    return jsonify({'success': True, 'users': items})


@app.route('/api/admin/users', methods=['POST'])
def admin_create_user():
    """管理员：手动创建账号（无需邀请码）"""
    denied = _require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    if not _valid_username(username):
        return jsonify({'success': False, 'error': '用户名需为2-32位字母、数字、下划线或连字符'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': '密码至少需要6位'}), 400
    with _USERS_LOCK:
        users = _load_users()
        if username in users:
            return jsonify({'success': False, 'error': '该用户名已存在'}), 400
        users[username] = {
            'password_hash': generate_password_hash(password),
            'is_admin': bool(data.get('is_admin', False)),
            'created_at': datetime.now().isoformat(),
        }
        _save_users(users)
    return jsonify({'success': True, 'username': username})


@app.route('/api/admin/users/<username>', methods=['DELETE'])
def admin_delete_user(username):
    """管理员：删除用户（连同其数据目录；不能删除自己和最后一个管理员）"""
    denied = _require_admin()
    if denied:
        return denied
    if username == _user():
        return jsonify({'success': False, 'error': '不能删除自己的账号'}), 400
    with _USERS_LOCK:
        users = _load_users()
        if username not in users:
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        if users[username].get('is_admin'):
            admins = [u for u, r in users.items() if r.get('is_admin')]
            if len(admins) <= 1:
                return jsonify({'success': False, 'error': '不能删除最后一个管理员'}), 400
        del users[username]
        _save_users(users)
    delete_user_data(username)
    return jsonify({'success': True})


@app.route('/api/admin/users/<username>/reset-password', methods=['POST'])
def admin_reset_password(username):
    """管理员：重置某用户密码（该用户所有旧会话立即失效）"""
    denied = _require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    new_password = str(data.get('new_password', ''))
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': '新密码至少需要6位'}), 400
    with _USERS_LOCK:
        users = _load_users()
        if username not in users:
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        users[username]['password_hash'] = generate_password_hash(new_password)
        _save_users(users)
    return jsonify({'success': True, 'message': f'已重置 {username} 的密码，该用户的旧登录已全部失效'})


def _require_admin():
    """管理员接口守卫：返回None表示通过，否则返回403响应"""
    if _auth_mode() != 'multi' or not g.get('is_admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    return None


@app.route('/api/providers')
def get_providers():
    """获取所有提供商列表（多用户模式下自定义服务商按用户隔离）"""
    providers = list_providers(user=_user())
    return jsonify(providers)


@app.route('/api/balance', methods=['POST'])
def query_balance():
    """查询余额"""
    data = request.get_json()
    provider_key = data.get('provider')
    api_key = data.get('api_key')

    if not provider_key or not api_key:
        return jsonify({
            'success': False,
            'error': '缺少参数'
        })

    provider = get_provider_by_key(provider_key, _user())
    if not provider:
        if provider_key == 'custom':
            error = '请先填写配置并保存，再查询'
        elif provider_key.startswith('custom_'):
            error = '该自定义服务商不存在或已删除'
        else:
            error = f'未知的服务商: {provider_key}'
        return jsonify({
            'success': False,
            'error': error
        })

    checker = TokenBalanceChecker(provider, api_key)
    success, result, error = checker.get_balance()

    if success:
        currency = 'CNY'
        if result and len(result) > 0:
            currency = result[0].get('currency', 'CNY')
        return jsonify({
            'success': True,
            'data': result,
            'currency': currency
        })
    else:
        return jsonify({
            'success': False,
            'error': error
        })


@app.route('/api/usage', methods=['POST'])
def query_usage():
    """查询用量"""
    data = request.get_json()
    provider_key = data.get('provider')
    api_key = data.get('api_key')

    if not provider_key or not api_key:
        return jsonify({
            'success': False,
            'error': '缺少参数'
        })

    provider = get_provider_by_key(provider_key, _user())
    if not provider:
        if provider_key == 'custom':
            error = '请先填写配置并保存，再查询'
        elif provider_key.startswith('custom_'):
            error = '该自定义服务商不存在或已删除'
        else:
            error = f'未知的服务商: {provider_key}'
        return jsonify({
            'success': False,
            'error': error
        })

    checker = TokenBalanceChecker(provider, api_key)
    success, result, error = checker.get_usage()

    if success:
        currency = result.get('currency', 'CNY') if result else 'CNY'
        return jsonify({
            'success': True,
            'data': result,
            'currency': currency
        })
    else:
        return jsonify({
            'success': False,
            'error': error
        })


@app.route('/api/custom-providers', methods=['GET'])
def list_custom_providers_route():
    """获取全部自定义服务商配置"""
    return jsonify({'success': True, 'providers': get_custom_configs(user=_user())})


@app.route('/api/custom-config', methods=['POST'])
def save_custom_config_route():
    """新增或更新自定义服务商（带id为更新，不带为新增）"""
    data = request.get_json() or {}
    if not data.get('base_url'):
        return jsonify({'success': False, 'error': 'API 地址不能为空'})
    cid, cfg = save_custom_config(data, data.get('id', ''), user=_user())
    return jsonify({'success': True, 'id': cid, 'config': cfg})


@app.route('/api/custom-config/<cid>', methods=['DELETE'])
def delete_custom_config_route(cid):
    """删除自定义服务商，同时删除其已保存的密钥文件"""
    if not delete_custom_config(cid, user=_user()):
        return jsonify({'success': False, 'error': '该自定义服务商不存在'})
    key_file = os.path.join(token_core.get_config_dir(_user()), f'.{cid}_key')
    try:
        if os.path.exists(key_file):
            os.remove(key_file)
    except Exception:
        pass
    return jsonify({'success': True})


@app.route('/api/pricing')
def get_pricing_route():
    """获取traktoken.com实时价格表（按性价比降序，含峰/谷状态，按北京时间）"""
    return jsonify(get_pricing())


@app.route('/api/keys/<provider_key>', methods=['GET'])
def get_saved_key(provider_key):
    """获取该服务商最近保存的Token（用于切换服务商时回填）"""
    tokens = list_tokens(provider_key, user=_user())
    if tokens:
        t = tokens[0]
        return jsonify({'success': True, 'id': t['id'], 'token': t['token'], 'note': t.get('note', '')})
    return jsonify({'success': True, 'id': '', 'token': '', 'note': ''})


@app.route('/api/keys/<provider_key>', methods=['POST'])
def save_key(provider_key):
    """新增/更新Token（同一服务商可保存多个；相同Token自动更新备注）"""
    data = request.get_json() or {}
    api_key = data.get('api_key')
    note = data.get('note', '')

    if not api_key:
        return jsonify({'success': False, 'error': '缺少 API Key'})

    if provider_key == 'custom':
        return jsonify({'success': False, 'error': '请先填写自定义服务商配置并保存'})

    ok, msg, _added = add_token(provider_key, api_key, note, user=_user())
    return jsonify({'success': ok, 'message': msg, 'error': None if ok else msg})


@app.route('/api/keys', methods=['GET'])
def list_saved_keys():
    """列出全部已保存Token（含实时服务商名与备注）"""
    names = {p['key']: p['name'] for p in list_providers(user=_user())}
    keys = []
    for t in list_tokens(user=_user()):
        keys.append({
            'id': t['id'],
            'provider_key': t['provider'],
            'provider_name': names.get(t['provider'], t['provider']),
            'api_key': t['token'],
            'note': t.get('note', ''),
            'saved_at': t.get('saved_at', '')
        })
    return jsonify(keys)


@app.route('/api/tokens/<token_id>', methods=['DELETE'])
def delete_token_route(token_id):
    """删除一条已保存的Token"""
    ok = delete_token(token_id, user=_user())
    return jsonify({'success': ok, 'message': 'Token已删除' if ok else 'Token不存在',
                    'error': None if ok else 'Token不存在'})


@app.route('/api/tokens/<token_id>/note', methods=['POST'])
def update_token_note_route(token_id):
    """更新某条Token的备注"""
    data = request.get_json() or {}
    ok = update_token_note(token_id, data.get('note', ''), user=_user())
    return jsonify({'success': ok, 'message': '备注已保存' if ok else 'Token不存在',
                    'error': None if ok else 'Token不存在'})


def main():
    print("=" * 60)
    print("Token Manager Web Server (Docker)")
    print("=" * 60)
    print("\n支持的AI API提供商:")
    for p in list_providers():
        print(f"  - {p['name']}")
    print("\n" + "=" * 60)
    print(f"启动服务: http://0.0.0.0:{os.environ.get('PORT', '5000')}")
    print(f"密钥保存目录: {DATA_DIR}")
    mode = _auth_mode()
    validity = "浏览器会话（关闭浏览器即失效）" if SESSION_DAYS == 0 else f"{SESSION_DAYS:g} 天"
    if mode == 'multi':
        invite = "需要邀请码（ACCESS_CODE）" if ACCESS_CODE else "开放注册"
        print(f"👥 多用户模式: 已启用，注册{invite}，登录有效期 {validity}")
    elif mode == 'code':
        print(f"🔒 访问码鉴权: 已启用，登录有效期 {validity}")
    else:
        print("⚠️  未启用鉴权：未设置 ACCESS_CODE 且未开启 MULTI_USER，界面无需登录即可访问")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)


if __name__ == '__main__':
    main()
