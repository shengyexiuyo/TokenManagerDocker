#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Token Manager Core - AI API余额查询核心功能
纯Python模块，无GUI依赖
"""

import requests
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class APIProvider(ABC):
    """API提供商抽象基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def key(self) -> str:
        pass
    
    @property
    @abstractmethod
    def balance_endpoint(self) -> str:
        pass
    
    @property
    @abstractmethod
    def usage_endpoint(self) -> str:
        pass
    
    @property
    @abstractmethod
    def auth_type(self) -> str:
        pass
    
    @property
    @abstractmethod
    def dashboard_url(self) -> str:
        pass
    
    @abstractmethod
    def parse_balance(self, data: dict) -> list:
        pass
    
    @abstractmethod
    def parse_usage(self, data: dict) -> dict:
        pass
    
    @abstractmethod
    def validate_api_key(self, api_key: str) -> bool:
        pass


class DeepSeekProvider(APIProvider):
    @property
    def name(self): return "DeepSeek"
    @property
    def key(self): return "deepseek"
    @property
    def balance_endpoint(self): return "https://api.deepseek.com/user/balance"
    @property
    def usage_endpoint(self): return "https://api.deepseek.com/user/balance"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://platform.deepseek.com/"
    def parse_balance(self, data: dict) -> list:
        balance_list = data.get('balance_infos', [])
        result = []
        for item in balance_list:
            result.append({
                'currency': item.get('currency', 'CNY'),
                'total': float(item.get('total_balance', '0')),
                'granted': float(item.get('granted_balance', '0')),
                'topped_up': float(item.get('topped_up_balance', '0')),
                'available': float(item.get('total_balance', '0'))
            })
        return result
    def parse_usage(self, data: dict) -> dict:
        balance_list = data.get('balance_infos', [])
        if balance_list:
            item = balance_list[0]
            return {
                'currency': item.get('currency', 'CNY'),
                'used_today': 0,
                'used_month': 0,
                'total_used': float(item.get('total_balance', '0')) - float(item.get('available_balance', item.get('total_balance', '0')))
            }
        return {'currency': 'CNY', 'used_today': 0, 'used_month': 0, 'total_used': 0}
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('sk-')


class OpenAIProvider(APIProvider):
    @property
    def name(self): return "OpenAI"
    @property
    def key(self): return "openai"
    @property
    def balance_endpoint(self): return "https://api.openai.com/v1/dashboard/billing/subscription"
    @property
    def usage_endpoint(self): return "https://api.openai.com/v1/dashboard/billing/usage"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://platform.openai.com/"
    def parse_balance(self, data: dict) -> list:
        # 订阅接口只返回额度上限，剩余额度由TokenBalanceChecker结合用量接口计算
        return [{
            'currency': 'USD',
            'total': float(data.get('hard_limit_usd', 0)),
            'granted': 0,
            'topped_up': float(data.get('hard_limit_usd', 0)),
            'available': float(data.get('hard_limit_usd', 0)),
            'has_subscription': data.get('has_payment_method', False),
            'plan_name': data.get('plan', {}).get('title', 'N/A')
        }]
    def parse_usage(self, data: dict) -> dict:
        daily_costs = data.get('daily_costs', [])
        today_usage = 0
        if daily_costs:
            last_day = daily_costs[-1]
            today_usage = sum(item.get('cost', 0) for item in last_day.get('line_items', []))

        # total_usage单位为美分
        month_usage = float(data.get('total_usage', 0)) / 100.0
        return {
            'currency': 'USD',
            'used_today': round(today_usage, 4),
            'used_month': round(month_usage, 4),
            'total_used': round(month_usage, 4)
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('sk-')


class DoubaoLiteProvider(APIProvider):
    @property
    def name(self): return "Doubao"
    @property
    def key(self): return "doubao"
    @property
    def balance_endpoint(self): return "https://ark.cn-beijing.volces.com/api/usage/v1/balance"
    @property
    def usage_endpoint(self): return "https://ark.cn-beijing.volces.com/api/usage/v1/query"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://console.volcengine.com/ark"
    def parse_balance(self, data: dict) -> list:
        return [{
            'currency': data.get('currency', 'CNY'),
            'total': float(data.get('balance', 0)),
            'granted': float(data.get('granted_balance', 0)),
            'topped_up': float(data.get('topped_up_balance', 0)),
            'available': float(data.get('balance', 0))
        }]
    def parse_usage(self, data: dict) -> dict:
        return {
            'currency': data.get('currency', 'CNY'),
            'used_today': float(data.get('daily_used', 0)),
            'used_month': float(data.get('monthly_used', 0)),
            'total_used': float(data.get('total_used', 0))
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('ak-') or len(api_key) > 20


class QwenProvider(APIProvider):
    @property
    def name(self): return "Qwen"
    @property
    def key(self): return "qwen"
    @property
    def balance_endpoint(self): return "https://dashscope.aliyuncs.com/api/v1/usage"
    @property
    def usage_endpoint(self): return "https://dashscope.aliyuncs.com/api/v1/usage"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://bailian.console.aliyun.com"
    def parse_balance(self, data: dict) -> list:
        return [{
            'currency': data.get('currency', 'CNY'),
            'total': float(data.get('total_balance', 0)),
            'granted': float(data.get('granted_balance', 0)),
            'topped_up': float(data.get('topped_up_balance', 0)),
            'available': float(data.get('available_balance', 0))
        }]
    def parse_usage(self, data: dict) -> dict:
        return {
            'currency': data.get('currency', 'CNY'),
            'used_today': float(data.get('daily_cost', 0)),
            'used_month': float(data.get('monthly_cost', 0)),
            'total_used': float(data.get('total_cost', 0))
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('sk-') and len(api_key) > 40


class HunyuanProvider(APIProvider):
    @property
    def name(self): return "Tencent"
    @property
    def key(self): return "hunyuan"
    @property
    def balance_endpoint(self): return "https://hunyuan.cloud.tencent.com/api/v1/balance"
    @property
    def usage_endpoint(self): return "https://hunyuan.cloud.tencent.com/api/v1/usage"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://console.cloud.tencent.com/hunyuan"
    def parse_balance(self, data: dict) -> list:
        return [{
            'currency': data.get('currency', 'CNY'),
            'total': float(data.get('total_balance', 0)),
            'granted': float(data.get('granted_balance', 0)),
            'topped_up': float(data.get('topped_up_balance', 0)),
            'available': float(data.get('available_balance', 0))
        }]
    def parse_usage(self, data: dict) -> dict:
        return {
            'currency': data.get('currency', 'CNY'),
            'used_today': float(data.get('daily_used', 0)),
            'used_month': float(data.get('monthly_used', 0)),
            'total_used': float(data.get('total_used', 0))
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('sk-') and len(api_key) > 40


class ZhipuProvider(APIProvider):
    @property
    def name(self): return "GLM"
    @property
    def key(self): return "zhipu"
    @property
    def balance_endpoint(self): return "https://open.bigmodel.cn/api/biz/account/query-customer-account-report"
    @property
    def usage_endpoint(self): return "https://open.bigmodel.cn/api/biz/account/query-customer-account-report"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://open.bigmodel.cn/console"
    def parse_balance(self, data: dict) -> list:
        data_obj = data.get('data', data)
        return [{
            'currency': 'CNY',
            'total': float(data_obj.get('rechargeAmount', 0)) + float(data_obj.get('giveAmount', 0)),
            'granted': float(data_obj.get('giveAmount', 0)),
            'topped_up': float(data_obj.get('rechargeAmount', 0)),
            'available': float(data_obj.get('availableBalance', 0))
        }]
    def parse_usage(self, data: dict) -> dict:
        data_obj = data.get('data', data)
        total_used = float(data_obj.get('totalSpendAmount', 0))
        return {
            'currency': 'CNY',
            'used_today': 0,
            'used_month': 0,
            'total_used': total_used
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('glm-') or len(api_key) > 30


class MimoProvider(APIProvider):
    # 注意：MiMo余额接口不走API Key，而是浏览器登录后的Cookie（serviceToken等），有效期约24小时
    @property
    def name(self): return "Mimo"
    @property
    def key(self): return "mimo"
    @property
    def balance_endpoint(self): return "https://platform.xiaomimimo.com/api/v1/balance"
    @property
    def usage_endpoint(self): return "https://platform.xiaomimimo.com/api/v1/tokenPlan/usage"
    @property
    def auth_type(self): return "cookie"
    @property
    def dashboard_url(self): return "https://platform.xiaomimimo.com/console/balance"
    def parse_balance(self, data: dict) -> list:
        if data.get('code') != 0:
            raise ValueError(str(data.get('msg', data.get('message', '查询失败'))))
        data_obj = data.get('data', {}) or {}
        currency = data_obj.get('currency', 'CNY')
        total = float(data_obj.get('balance', 0))
        return [{
            'currency': currency,
            'total': total,
            'granted': float(data_obj.get('giftBalance', 0)),
            'topped_up': float(data_obj.get('cashBalance', 0)),
            'available': total,
            'frozen': float(data_obj.get('frozenBalance', 0)),
            'overdraft_limit': float(data_obj.get('overdraftLimit', 0))
        }]
    def parse_usage(self, data: dict) -> dict:
        if data.get('code') != 0:
            raise ValueError(str(data.get('msg', data.get('message', '查询失败'))))
        items = ((data.get('data', {}) or {}).get('usage', {}) or {}).get('items', []) or []
        plan_total = sum(float(item.get('plan_total_token', 0)) for item in items)
        compensation_total = sum(float(item.get('compensation_total_token', 0)) for item in items)
        return {
            'currency': '百万积分',
            'used_today': 0,
            'used_month': 0,
            'total_used': round((plan_total + compensation_total) / 1000000.0, 2)
        }
    def validate_api_key(self, api_key: str) -> bool:
        return len(api_key) > 20


class KimiProvider(APIProvider):
    @property
    def name(self): return "Kimi"
    @property
    def key(self): return "kimi"
    @property
    def balance_endpoint(self): return "https://api.moonshot.cn/v1/users/me/balance"
    @property
    def usage_endpoint(self): return "https://api.moonshot.cn/v1/users/me/balance"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://platform.moonshot.cn"
    def parse_balance(self, data: dict) -> list:
        data_obj = data.get('data', data) or {}
        available = float(data_obj.get('available_balance', 0))
        return [{
            'currency': 'CNY',
            'total': available,
            'granted': float(data_obj.get('voucher_balance', 0)),
            'topped_up': float(data_obj.get('cash_balance', 0)),
            'available': available
        }]
    def parse_usage(self, data: dict) -> dict:
        # Kimi官方未提供用量查询API
        return {
            'currency': 'CNY',
            'used_today': 0,
            'used_month': 0,
            'total_used': 0
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('sk-') and '-moonshot-' in api_key


class ClaudeProvider(APIProvider):
    @property
    def name(self): return "Claude"
    @property
    def key(self): return "claude"
    @property
    def balance_endpoint(self): return "https://api.anthropic.com/v1/organizations/current/credit_summary"
    @property
    def usage_endpoint(self): return "https://api.anthropic.com/v1/organizations/current/credit_summary"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://console.anthropic.com/"
    def parse_balance(self, data: dict) -> list:
        return [{
            'currency': 'USD',
            'total': float(data.get('credit_balance', 0)),
            'granted': float(data.get('free_credits_remaining', 0)),
            'topped_up': float(data.get('purchased_credits', 0)),
            'available': float(data.get('credit_balance', 0))
        }]
    def parse_usage(self, data: dict) -> dict:
        return {
            'currency': 'USD',
            'used_today': float(data.get('daily_usage', 0)),
            'used_month': float(data.get('monthly_usage', 0)),
            'total_used': float(data.get('total_usage', 0))
        }
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('sk-ant-')


class GeminiProvider(APIProvider):
    """Google Gemini：官方未提供余额查询API，此接口用于验证Key有效性并列出可用模型"""
    @property
    def name(self): return "Gemini"
    @property
    def key(self): return "gemini"
    @property
    def balance_endpoint(self): return "https://generativelanguage.googleapis.com/v1beta/models"
    @property
    def usage_endpoint(self): return "https://generativelanguage.googleapis.com/v1beta/models"
    @property
    def auth_type(self): return "x_api_key"
    @property
    def dashboard_url(self): return "https://aistudio.google.com/"
    def parse_balance(self, data: dict) -> list:
        models = data.get('models', []) or []
        return [{
            'currency': 'USD',
            'total': 0, 'granted': 0, 'topped_up': 0, 'available': 0,
            'note': f'Google未提供余额查询API，Key有效，可用模型 {len(models)} 个（余额请登录 aistudio.google.com 查看）'
        }]
    def parse_usage(self, data: dict) -> dict:
        return {'currency': 'USD', 'used_today': 0, 'used_month': 0, 'total_used': 0}
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('AIza')


class MiniMaxProvider(APIProvider):
    """MiniMax：官方未提供余额查询API，此接口用于验证Key有效性"""
    @property
    def name(self): return "MiniMax"
    @property
    def key(self): return "minimax"
    @property
    def balance_endpoint(self): return "https://api.minimax.chat/v1/models"
    @property
    def usage_endpoint(self): return "https://api.minimax.chat/v1/models"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://platform.minimaxi.com/"
    def parse_balance(self, data: dict) -> list:
        models = data.get('models', []) or (data.get('data') or {}).get('models', []) or []
        note = f'MiniMax未提供余额查询API，Key有效，可用模型 {len(models)} 个'
        return [{
            'currency': 'CNY',
            'total': 0, 'granted': 0, 'topped_up': 0, 'available': 0,
            'note': note
        }]
    def parse_usage(self, data: dict) -> dict:
        return {'currency': 'CNY', 'used_today': 0, 'used_month': 0, 'total_used': 0}
    def validate_api_key(self, api_key: str) -> bool:
        return len(api_key) > 10


class MetaProvider(APIProvider):
    """Meta Llama API：官方未提供余额查询API，此接口用于验证Key有效性"""
    @property
    def name(self): return "Meta"
    @property
    def key(self): return "meta"
    @property
    def balance_endpoint(self): return "https://api.llama.com/v1/models"
    @property
    def usage_endpoint(self): return "https://api.llama.com/v1/models"
    @property
    def auth_type(self): return "bearer"
    @property
    def dashboard_url(self): return "https://llama.developer.meta.com/"
    def parse_balance(self, data: dict) -> list:
        models = data.get('models', []) or (data.get('data') or {}).get('models', []) or []
        note = f'Meta未提供余额查询API，Key有效，可用模型 {len(models)} 个'
        return [{
            'currency': 'USD',
            'total': 0, 'granted': 0, 'topped_up': 0, 'available': 0,
            'note': note
        }]
    def parse_usage(self, data: dict) -> dict:
        return {'currency': 'USD', 'used_today': 0, 'used_month': 0, 'total_used': 0}
    def validate_api_key(self, api_key: str) -> bool:
        return api_key.startswith('LLM|') or len(api_key) > 10


# ==================== 自定义服务商 ====================

CUSTOM_CONFIG_FILE = '.custom_providers.json'
LEGACY_CUSTOM_FILE = '.custom_provider.json'


def _get_config_dir() -> str:
    """配置文件目录：Docker中为DATA_DIR，打包exe为exe所在目录，开发时为代码目录"""
    if os.environ.get('DATA_DIR'):
        return os.environ['DATA_DIR']
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_custom_configs() -> dict:
    """全部自定义服务商配置 {id: cfg}；首次读取时自动迁移旧版单配置文件"""
    path = os.path.join(_get_config_dir(), CUSTOM_CONFIG_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return data
    except Exception:
        pass
    legacy_path = os.path.join(_get_config_dir(), LEGACY_CUSTOM_FILE)
    try:
        with open(legacy_path, 'r', encoding='utf-8') as f:
            legacy = json.load(f)
        if isinstance(legacy, dict) and legacy.get('base_url'):
            legacy.pop('updated_at', None)
            cfgs = {'custom_migrated': legacy}
            _write_custom_configs(cfgs)
            return cfgs
    except Exception:
        pass
    return {}


def _write_custom_configs(cfgs: dict):
    config_dir = _get_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, CUSTOM_CONFIG_FILE), 'w', encoding='utf-8') as f:
        json.dump(cfgs, f, ensure_ascii=False, indent=2)


def save_custom_config(cfg: dict, cid: str = '') -> tuple:
    """新增或更新自定义服务商，返回(域名内的id, 保存后的配置)"""
    cfgs = get_custom_configs()
    cid = cid if cid and cid in cfgs else 'custom_' + secrets.token_hex(3)
    saved = {k: str(v).strip() for k, v in (cfg or {}).items()}
    saved['updated_at'] = datetime.now().isoformat()
    cfgs[cid] = saved
    _write_custom_configs(cfgs)
    return cid, saved


def delete_custom_config(cid: str) -> bool:
    cfgs = get_custom_configs()
    if cid in cfgs:
        del cfgs[cid]
        _write_custom_configs(cfgs)
        return True
    return False


class CustomProvider(APIProvider):
    """自定义服务商：按中转站(one-api/new-api)的OpenAI兼容计费接口常规实现
    余额接口返回 hard_limit_usd 作为额度上限；用量接口返回 total_usage（单位为美分）"""
    def __init__(self, cfg: Optional[dict] = None, key: str = 'custom'):
        self._cfg = cfg or {}
        self._name = self._cfg.get('name') or '自定义'
        self._key = key
        self._base = (self._cfg.get('base_url') or '').rstrip('/')
        self._balance_path = self._cfg.get('balance_path') or '/dashboard/billing/subscription'
        self._usage_path = self._cfg.get('usage_path') or '/dashboard/billing/usage'
        self._currency = self._cfg.get('currency') or 'USD'

    @property
    def name(self): return self._name
    @property
    def key(self): return self._key
    @property
    def balance_endpoint(self): return self._base + self._balance_path
    @property
    def usage_endpoint(self): return self._base + self._usage_path
    @property
    def auth_type(self): return 'bearer'
    @property
    def dashboard_url(self): return self._base
    def parse_balance(self, data: dict) -> list:
        total = data.get('hard_limit_usd')
        if total is None:
            # 兼容部分中转站的自定义返回字段
            for k in ('balance', 'total_balance', 'quota'):
                if data.get(k) is not None:
                    total = data[k]
                    break
        try:
            total = float(total or 0)
        except (TypeError, ValueError):
            total = 0
        return [{'currency': self._currency, 'total': total,
                 'granted': 0, 'topped_up': total, 'available': total}]
    def parse_usage(self, data: dict) -> dict:
        try:
            used = float(data.get('total_usage', 0)) / 100.0
        except (TypeError, ValueError):
            used = 0
        return {'currency': self._currency, 'used_today': 0,
                'used_month': used, 'total_used': used}
    def validate_api_key(self, api_key: str) -> bool:
        return len(api_key) > 8


def get_config_dir() -> str:
    """配置目录（密钥文件所在目录），供桌面版等直接调用"""
    return _get_config_dir()


# ==================== 多Token存储（每个服务商可保存多个Token） ====================

TOKENS_FILE = '.tokens.json'


def _write_tokens(tokens: list):
    config_dir = _get_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, TOKENS_FILE), 'w', encoding='utf-8') as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def _migrate_legacy_keys(tokens: list) -> list:
    """把旧版单Token文件(.XX_key)导入为多Token条目（按服务商+Token去重，可重复调用）"""
    known = {(t['provider'], t['token']) for t in tokens}
    for p in list_providers():
        path = os.path.join(_get_config_dir(), f'.{p["key"]}_key')
        try:
            if not os.path.exists(path):
                continue
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            token = data.get('api_key', '')
            if not token or (p['key'], token) in known:
                continue
            tokens.append({
                'id': 't_' + secrets.token_hex(4),
                'provider': p['key'],
                'token': token,
                'note': str(data.get('note', '')).strip(),
                'saved_at': data.get('saved_at', datetime.now().isoformat()),
            })
        except Exception:
            pass
    return tokens


def _load_tokens() -> list:
    path = os.path.join(_get_config_dir(), TOKENS_FILE)
    tokens = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            tokens = [t for t in data if isinstance(t, dict) and t.get('token')]
    except Exception:
        tokens = []
    before = len(tokens)
    tokens = _migrate_legacy_keys(tokens)
    path_exists = os.path.exists(path)
    if len(tokens) != before or not path_exists:
        _write_tokens(tokens)
    return tokens


def list_tokens(provider_key: str = '') -> list:
    """全部已保存Token（可按服务商过滤），按保存时间倒序"""
    tokens = _load_tokens()
    if provider_key:
        tokens = [t for t in tokens if t['provider'] == provider_key]
    return sorted(tokens, key=lambda t: t.get('saved_at', ''), reverse=True)


def add_token(provider_key: str, api_key: str, note: str = '') -> tuple:
    """新增Token；同一服务商下相同Token则更新备注（upsert）
    返回(是否成功, 消息, 是否为新增)"""
    provider = get_provider_by_key(provider_key)
    if not provider:
        reason = '自定义服务商不存在' if provider_key.startswith('custom') else '未知的服务商'
        return False, reason, False
    if not provider.validate_api_key(api_key):
        return False, 'API Key 格式不正确', False
    tokens = _load_tokens()
    for t in tokens:
        if t['provider'] == provider_key and t['token'] == api_key:
            if str(note or '').strip():
                t['note'] = str(note).strip()
            t['saved_at'] = datetime.now().isoformat()
            _write_tokens(tokens)
            return True, '该Token已存在，备注已更新', False
    tokens.append({
        'id': 't_' + secrets.token_hex(4),
        'provider': provider_key,
        'token': api_key,
        'note': str(note or '').strip(),
        'saved_at': datetime.now().isoformat()
    })
    _write_tokens(tokens)
    return True, 'Token已保存', True


def update_token_note(token_id: str, note: str) -> bool:
    """更新某条Token的备注"""
    tokens = _load_tokens()
    for t in tokens:
        if t['id'] == token_id:
            t['note'] = str(note or '').strip()
            _write_tokens(tokens)
            return True
    return False


def delete_token(token_id: str) -> bool:
    tokens = _load_tokens()
    rest = [t for t in tokens if t['id'] != token_id]
    if len(rest) != len(tokens):
        _write_tokens(rest)
        return True
    return False


def get_token(token_id: str) -> Optional[dict]:
    """按id取单条Token"""
    for t in _load_tokens():
        if t['id'] == token_id:
            return t
    return None


def get_custom_provider(key: str) -> Optional[CustomProvider]:
    """按key返回已配置的自定义服务商（key形如custom_xxxx），不存在返回None"""
    cfg = get_custom_configs().get(key)
    if not cfg or not cfg.get('base_url'):
        return None
    return CustomProvider(cfg, key=key)


API_PROVIDERS = {
    'deepseek': DeepSeekProvider(),
    'openai': OpenAIProvider(),
    'doubao': DoubaoLiteProvider(),
    'qwen': QwenProvider(),
    'hunyuan': HunyuanProvider(),
    'zhipu': ZhipuProvider(),
    'mimo': MimoProvider(),
    'kimi': KimiProvider(),
    'claude': ClaudeProvider(),
    'gemini': GeminiProvider(),
    'meta': MetaProvider(),
    'minimax': MiniMaxProvider(),
}


class TokenBalanceChecker:
    """Token余额查询核心类"""
    
    def __init__(self, provider: APIProvider, api_key: str):
        self.provider = provider
        self.api_key = api_key
        self.session = requests.Session()
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        if self.provider.auth_type == "bearer":
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        elif self.provider.auth_type == "api_key":
            return {
                "api-key": self.api_key,
                "Content-Type": "application/json"
            }
        elif self.provider.auth_type == "cookie":
            return {
                "Cookie": self.api_key,
                "Accept": "application/json",
                "User-Agent": "TokenManager/1.0"
            }
        elif self.provider.auth_type == "x_api_key":
            return {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json"
            }
        return {"Authorization": f"Bearer {self.api_key}"}
    
    def get_balance(self) -> tuple[bool, Any, str]:
        """查询余额"""
        try:
            headers = self._get_headers()
            response = self.session.get(
                self.provider.balance_endpoint,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # 部分API返回200但success为false
                if data.get('success') is False:
                    return False, None, f"查询失败: {data.get('msg', data.get('message', '未知错误'))}"
                balance_list = self.provider.parse_balance(data)
                # OpenAI/自定义服务商的订阅接口只返回额度上限，需再查当月用量计算剩余额度
                if self.provider.key in ('openai', 'custom') and balance_list:
                    ok, usage, _ = self.get_usage()
                    if ok and usage:
                        used = float(usage.get('used_month', 0))
                        total = float(balance_list[0].get('total', 0))
                        balance_list[0]['available'] = round(max(total - used, 0), 4)
                        balance_list[0]['total_used'] = used
                return True, balance_list, ""
            elif response.status_code == 401:
                return False, None, "API密钥无效或已过期"
            elif response.status_code == 403:
                return False, None, "API密钥权限不足"
            else:
                return False, None, f"请求失败: {response.status_code} - {response.text}"
        except requests.exceptions.Timeout:
            return False, None, "请求超时"
        except requests.exceptions.ConnectionError:
            return False, None, "网络连接失败"
        except Exception as e:
            return False, None, f"查询失败: {str(e)}"
    
    def get_usage(self) -> tuple[bool, Any, str]:
        """查询用量"""
        try:
            headers = self._get_headers()
            
            # OpenAI及自定义服务商（中转站约定）需要日期参数
            if self.provider.key in ('openai', 'custom'):
                now = datetime.now()
                start_date = f"{now.year}-{now.month:02d}-01"
                next_month = now.month + 1 if now.month < 12 else 1
                next_year = now.year if now.month < 12 else now.year + 1
                end_date = f"{next_year}-{next_month:02d}-01"
                
                params = {
                    "start_date": start_date,
                    "end_date": end_date
                }
                response = self.session.get(
                    self.provider.usage_endpoint,
                    headers=headers,
                    params=params,
                    timeout=30
                )
            else:
                response = self.session.get(
                    self.provider.usage_endpoint,
                    headers=headers,
                    timeout=30
                )
            
            if response.status_code == 200:
                data = response.json()
                # 部分API返回200但success为false
                if data.get('success') is False:
                    return False, None, f"查询失败: {data.get('msg', data.get('message', '未知错误'))}"
                usage = self.provider.parse_usage(data)
                return True, usage, ""
            elif response.status_code == 401:
                return False, None, "API密钥无效或已过期"
            else:
                return False, None, f"请求失败: {response.status_code}"
        except requests.exceptions.Timeout:
            return False, None, "请求超时"
        except requests.exceptions.ConnectionError:
            return False, None, "网络连接失败"
        except Exception as e:
            return False, None, f"查询失败: {str(e)}"


def list_providers() -> List[Dict[str, str]]:
    """列出所有支持的提供商：内置 + 各自定义服务商 + 末尾的"自定义"新增入口"""
    providers = []
    for provider in API_PROVIDERS.values():
        providers.append({
            'key': provider.key,
            'name': provider.name,
            'dashboard': provider.dashboard_url
        })
    for cid, cfg in get_custom_configs().items():
        if cfg.get('base_url'):
            providers.append({
                'key': cid,
                'name': cfg.get('name') or '自定义',
                'dashboard': cfg.get('base_url') or ''
            })
    providers.append({'key': 'custom', 'name': '自定义', 'dashboard': ''})
    return providers


def get_provider_by_key(key: str) -> Optional[APIProvider]:
    """根据key获取提供商（custom_*为根据配置动态构建的自定义服务商）"""
    if key and key.startswith('custom'):
        return get_custom_provider(key)
    return API_PROVIDERS.get((key or '').lower())


# ==================== 实时价格（数据源：traktoken.com，含峰谷时段判断） ====================

TRAKTOKEN_URL = 'https://www.traktoken.com/'
_TRAK_CACHE = {'at': 0.0, 'rows': None}
_TRAK_CACHE_TTL = 600  # 缓存10分钟
_BEIJING_TZ = timezone(timedelta(hours=8))

# 已知峰谷定价规则（按北京时间判断，谷时价格为刊例价×discount）
PEAK_RULES = {
    'deepseek': {
        'valley_start': '00:30',
        'valley_end': '08:30',
        'discount': 0.5,
        'description': '每日 00:30-08:30（北京时间）为错峰谷时段，价格按刊例价5折计费',
    },
}

# traktoken厂商slug → 本应用provider key（用于峰谷状态匹配）
_VENDOR_KEY_MAP = {
    'deepseek': 'deepseek',
    'zai': 'zhipu', 'zhipu': 'zhipu',
    'alibaba': 'qwen', 'qwen': 'qwen',
    'tencent': 'hunyuan',
    'moonshot': 'kimi', 'kimi': 'kimi',
    'openai': 'openai',
    'anthropic': 'claude', 'claude': 'claude',
    'google': 'gemini', 'gemini': 'gemini',
    'meta': 'meta',
    'minimax': 'minimax',
    'xiaomi': 'mimo', 'mimo': 'mimo',
}


def _parse_hhmm(text: str) -> int:
    try:
        h, m = str(text).split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return -1


def _in_valley_window(now: datetime, start: str, end: str) -> bool:
    """当前北京时间是否处于谷时段窗口内（支持跨午夜窗口）"""
    cur = now.hour * 60 + now.minute
    s, e = _parse_hhmm(start), _parse_hhmm(end)
    if s < 0 or e < 0:
        return False
    if s <= e:
        return s <= cur < e
    return cur >= s or cur < e


def _fetch_traktoken_rows() -> list:
    """抓取traktoken.com首页价格表（厂商/模型/输入输出价/性价比），结果缓存10分钟"""
    now_ts = time.time()
    if _TRAK_CACHE['rows'] is not None and now_ts - _TRAK_CACHE['at'] < _TRAK_CACHE_TTL:
        return _TRAK_CACHE['rows']

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    }
    resp = requests.get(TRAKTOKEN_URL, headers=headers, timeout=15)
    resp.raise_for_status()

    # 数据内嵌于Next.js flight负载（self.__next_f.push）中
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', resp.text, re.S)
    flight = ''.join(json.loads('"' + c + '"') for c in chunks)

    row_pat = re.compile(r'\["\$","tr","([^"]+)",\{"className".*?"children":\[(.*?)\]\]\}', re.S)
    vendor_pat = re.compile(r'"href":"/providers/([^"]+)"[^}]*?"children":"([^"]+)"')
    model_pat = re.compile(r'"href":"/models/([^"]+)"[^}]*?"children":"([^"]+)"')
    td_pat = re.compile(r'\["\$","td",null,\{[^\[\]]*?"children":(?:"((?:[^"\\]|\\.)*)"|(-?\d+(?:\.\d+)?))\}')

    rows = []
    for model_id, body in row_pat.findall(flight):
        v, m = vendor_pat.search(body), model_pat.search(body)
        if not v or not m:
            continue
        tds = td_pat.findall(body)
        # 价格td带"$$"前缀（React对字面$的转义），分数td为纯数字
        prices = [a for a, b in tds if a and a.startswith('$$')]
        score = next((b for a, b in tds if b), '')
        if len(prices) < 2:
            continue
        try:
            inp, out = float(prices[0].lstrip('$')), float(prices[1].lstrip('$'))
        except ValueError:
            continue
        slug, vendor = v.group(1), v.group(2)
        rows.append({
            'model_id': model_id,
            'vendor': vendor,
            'vendor_slug': slug,
            'model': m.group(2),
            'input': inp,
            'output': out,
            'score': score,
            'provider_key': _VENDOR_KEY_MAP.get(slug, ''),
        })
    if not rows:
        raise ValueError('未解析到价格数据')

    _TRAK_CACHE['rows'] = rows
    _TRAK_CACHE['at'] = now_ts
    return rows


def get_pricing() -> dict:
    """返回traktoken.com价格表（按性价比降序），并按北京时间附加当前峰/谷状态"""
    now = datetime.now(_BEIJING_TZ)
    result = {
        'success': True,
        'now': now.strftime('%Y-%m-%d %H:%M:%S'),
        'timezone': 'UTC+8（北京时间）',
        'source': 'traktoken.com',
        'rows': []
    }
    try:
        rows = _fetch_traktoken_rows()
    except Exception as e:
        result['success'] = False
        result['error'] = f'获取价格数据失败: {e}'
        return result

    for r in rows:
        row = dict(r)
        row['currency'] = 'USD'
        rule = PEAK_RULES.get(r['provider_key'])
        if rule:
            row['peak'] = '谷' if _in_valley_window(now, rule['valley_start'], rule['valley_end']) else '峰'
            row['peak_desc'] = rule['description']
        else:
            row['peak'] = None
            row['peak_desc'] = ''
        result['rows'].append(row)
    return result


def query_balance(provider_key: str, api_key: str) -> tuple[bool, Any, str]:
    """快速查询余额"""
    provider = get_provider_by_key(provider_key)
    if not provider:
        return False, None, f"未知提供商: {provider_key}"
    
    if not provider.validate_api_key(api_key):
        return False, None, "API密钥格式不正确"
    
    checker = TokenBalanceChecker(provider, api_key)
    return checker.get_balance()


def query_usage(provider_key: str, api_key: str) -> tuple[bool, Any, str]:
    """快速查询用量"""
    provider = get_provider_by_key(provider_key)
    if not provider:
        return False, None, f"未知提供商: {provider_key}"
    
    if not provider.validate_api_key(api_key):
        return False, None, "API密钥格式不正确"
    
    checker = TokenBalanceChecker(provider, api_key)
    return checker.get_usage()


if __name__ == "__main__":
    # 命令行测试
    print("支持的AI API提供商:")
    for p in list_providers():
        print(f"  - {p['name']} ({p['key']})")
    
    print("\n使用示例:")
    print("  from token_core import query_balance")
    print("  success, balance, error = query_balance('deepseek', 'sk-xxxxx')")
