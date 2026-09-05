#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Token Manager Web Server - Flask后端服务
提供REST API与前端daisyUI界面交互

Docker版：相比原版增加以下环境变量支持，其余逻辑保持一致
- DATA_DIR：密钥等配置的保存目录（Docker中指向挂载卷，默认为程序同目录）
- PORT：服务监听端口（默认5000）
- ACCESS_CODE：访问码（设置后进入界面和所有API都需要先输入，留空则不启用）
- SESSION_DAYS：登录有效期（天），默认30；0表示关闭浏览器后即需重新登录
"""

import sys
import os
import hmac
import hashlib

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

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import json

from token_core import (
    API_PROVIDERS,
    TokenBalanceChecker,
    add_token,
    delete_custom_config,
    delete_token,
    get_custom_configs,
    get_pricing,
    get_provider_by_key,
    list_providers,
    list_tokens,
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


def _auth_enabled() -> bool:
    """是否启用访问码"""
    return bool(ACCESS_CODE)


def _expected_token() -> str:
    """由访问码派生的会话令牌（无状态；修改访问码后所有旧会话自动失效）"""
    return hmac.new(ACCESS_CODE.encode('utf-8'), b'token-manager-auth-v1', hashlib.sha256).hexdigest()


def _is_authenticated() -> bool:
    token = request.cookies.get(AUTH_COOKIE) or request.headers.get('X-Auth-Token')
    return bool(token) and hmac.compare_digest(token, _expected_token())

app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path='')
CORS(app)


@app.after_request
def no_cache_html(resp):
    # 防止浏览器缓存旧版界面，导致更新后仍显示旧功能
    if resp.mimetype == 'text/html':
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

APP_VERSION = '1.3.0'


# 配置文件路径
def get_config_path(filename: str) -> str:
    """获取配置文件路径"""
    return os.path.join(DATA_DIR, filename)


@app.before_request
def auth_guard():
    """API统一鉴权：启用访问码后，除登录相关接口外都要求有效会话"""
    if not _auth_enabled():
        return None
    path = request.path
    if path.startswith('/api/auth/') or path == '/api/version':
        return None
    if path.startswith('/api/') and not _is_authenticated():
        return jsonify({
            'success': False,
            'error': '未登录或会话已过期，请刷新页面重新输入访问码'
        }), 401
    return None


@app.route('/')
@app.route('/index.html')
def index():
    """返回主页（启用访问码时，未登录则返回登录页）"""
    if _auth_enabled() and not _is_authenticated():
        return send_from_directory('gui', 'login.html')
    return send_from_directory('gui', 'index.html')


@app.route('/api/auth/check')
def auth_check():
    """检查鉴权状态（前端据此显示/隐藏退出登录按钮）"""
    return jsonify({
        'enabled': _auth_enabled(),
        'authenticated': _is_authenticated()
    })


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """校验访问码，成功后种下会话Cookie（30天有效）"""
    if not _auth_enabled():
        return jsonify({'success': True, 'message': '未启用访问码'})
    data = request.get_json(silent=True) or {}
    code = str(data.get('code', ''))
    if not code or not hmac.compare_digest(code, ACCESS_CODE):
        return jsonify({'success': False, 'error': '访问码错误'}), 401
    resp = jsonify({'success': True})
    cookie_kwargs = dict(httponly=True, samesite='Lax')
    if SESSION_DAYS > 0:
        cookie_kwargs['max_age'] = int(SESSION_DAYS * 24 * 3600)
    # SESSION_DAYS=0 时不设max_age，即浏览器会话Cookie，关闭浏览器后需重新登录
    resp.set_cookie(AUTH_COOKIE, _expected_token(), **cookie_kwargs)
    return resp


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """退出登录，清除会话Cookie"""
    resp = jsonify({'success': True})
    resp.delete_cookie(AUTH_COOKIE)
    return resp


@app.route('/api/version')
def version_route():
    """应用版本（用于确认部署的是否为新代码）"""
    return jsonify({'name': 'TokenManager', 'version': APP_VERSION})


@app.route('/api/providers')
def get_providers():
    """获取所有提供商列表"""
    providers = list_providers()
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

    provider = get_provider_by_key(provider_key)
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

    provider = get_provider_by_key(provider_key)
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
    return jsonify({'success': True, 'providers': get_custom_configs()})


@app.route('/api/custom-config', methods=['POST'])
def save_custom_config_route():
    """新增或更新自定义服务商（带id为更新，不带为新增）"""
    data = request.get_json() or {}
    if not data.get('base_url'):
        return jsonify({'success': False, 'error': 'API 地址不能为空'})
    cid, cfg = save_custom_config(data, data.get('id', ''))
    return jsonify({'success': True, 'id': cid, 'config': cfg})


@app.route('/api/custom-config/<cid>', methods=['DELETE'])
def delete_custom_config_route(cid):
    """删除自定义服务商，同时删除其已保存的密钥文件"""
    if not delete_custom_config(cid):
        return jsonify({'success': False, 'error': '该自定义服务商不存在'})
    key_file = get_config_path(f'.{cid}_key')
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
    tokens = list_tokens(provider_key)
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

    ok, msg, _added = add_token(provider_key, api_key, note)
    return jsonify({'success': ok, 'message': msg, 'error': None if ok else msg})


@app.route('/api/keys', methods=['GET'])
def list_saved_keys():
    """列出全部已保存Token（含实时服务商名与备注）"""
    names = {p['key']: p['name'] for p in list_providers()}
    keys = []
    for t in list_tokens():
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
    ok = delete_token(token_id)
    return jsonify({'success': ok, 'message': 'Token已删除' if ok else 'Token不存在',
                    'error': None if ok else 'Token不存在'})


@app.route('/api/tokens/<token_id>/note', methods=['POST'])
def update_token_note_route(token_id):
    """更新某条Token的备注"""
    data = request.get_json() or {}
    ok = update_token_note(token_id, data.get('note', ''))
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
    if _auth_enabled():
        validity = "浏览器会话（关闭浏览器即失效）" if SESSION_DAYS == 0 else f"{SESSION_DAYS:g} 天"
        print(f"🔒 访问码鉴权: 已启用，登录有效期 {validity}")
    else:
        print("⚠️  未设置 ACCESS_CODE 环境变量，界面无需访问码即可访问")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)


if __name__ == '__main__':
    main()
