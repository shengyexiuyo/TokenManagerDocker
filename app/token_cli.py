#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Token Manager CLI - 命令行版本
使用纯Python核心功能，无GUI
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from token_core import (
    list_providers,
    get_provider_by_key,
    query_balance,
    query_usage,
    API_PROVIDERS
)


def print_banner():
    print("=" * 60)
    print("Token Manager CLI - AI API余额查询工具")
    print("=" * 60)


def print_providers():
    print("\n支持的提供商:")
    for key, provider in API_PROVIDERS.items():
        print(f"  [{key:10}] {provider.name}")


def format_balance(balance_list, provider_name):
    """格式化余额输出"""
    print(f"\n{provider_name} 余额信息:")
    print("-" * 40)
    
    for item in balance_list:
        currency = item.get('currency', 'N/A')
        print(f"  货币单位: {currency}")
        print(f"  可用余额: {item.get('available', 0):.4f} {currency}")
        print(f"  总余额:   {item.get('total', 0):.4f} {currency}")
        print(f"  赠送额度: {item.get('granted', 0):.4f} {currency}")
        print(f"  充值余额: {item.get('topped_up', 0):.4f} {currency}")
        print()


def format_usage(usage, provider_name):
    """格式化用量输出"""
    print(f"\n{provider_name} 用量信息:")
    print("-" * 40)
    
    currency = usage.get('currency', 'N/A')
    print(f"  今日用量: {usage.get('used_today', 0):.4f} {currency}")
    print(f"  本月用量: {usage.get('used_month', 0):.4f} {currency}")
    print(f"  累计使用: {usage.get('total_used', 0):.4f} {currency}")
    print()


def main():
    print_banner()
    print_providers()
    
    # 如果有命令行参数，直接查询
    if len(sys.argv) >= 3:
        provider_key = sys.argv[1].lower()
        api_key = sys.argv[2]
        
        provider = get_provider_by_key(provider_key)
        if not provider:
            print(f"\n错误: 未知的提供商 '{provider_key}'")
            print_providers()
            sys.exit(1)
        
        # 查询余额
        print(f"\n正在查询 {provider.name} 余额...")
        success, balance, error = query_balance(provider_key, api_key)
        
        if success:
            format_balance(balance, provider.name)
        else:
            print(f"\n查询失败: {error}")
            sys.exit(1)
        
        # 查询用量
        print(f"正在查询 {provider.name} 用量...")
        success, usage, error = query_usage(provider_key, api_key)
        
        if success:
            format_usage(usage, provider.name)
        else:
            print(f"\n用量查询失败: {error}")
        
        print("=" * 60)
        return
    
    # 交互式模式
    print("\n" + "=" * 60)
    print("交互模式 - 输入 'quit' 退出")
    print("=" * 60)
    
    while True:
        try:
            print("\n请选择操作:")
            print("  1. 查询余额")
            print("  2. 列出所有提供商")
            print("  3. 退出")
            
            choice = input("\n请输入选项 (1/2/3): ").strip()
            
            if choice == '3' or choice.lower() == 'quit':
                print("\n再见!")
                break
            
            elif choice == '2':
                print_providers()
            
            elif choice == '1':
                print_providers()
                provider_key = input("\n请输入提供商key: ").strip().lower()
                
                provider = get_provider_by_key(provider_key)
                if not provider:
                    print(f"错误: 未知的提供商 '{provider_key}'")
                    continue
                
                api_key = input(f"请输入 {provider.name} 的API密钥: ").strip()
                
                print(f"\n正在查询 {provider.name} 余额...")
                success, balance, error = query_balance(provider_key, api_key)
                
                if success:
                    format_balance(balance, provider.name)
                else:
                    print(f"\n查询失败: {error}")
                    continue
                
                print(f"正在查询 {provider.name} 用量...")
                success, usage, error = query_usage(provider_key, api_key)
                
                if success:
                    format_usage(usage, provider.name)
                else:
                    print(f"\n用量查询失败: {error}")
            
            else:
                print("无效选项，请重新输入")
        
        except KeyboardInterrupt:
            print("\n\n再见!")
            break
        except Exception as e:
            print(f"\n错误: {e}")


if __name__ == "__main__":
    main()
