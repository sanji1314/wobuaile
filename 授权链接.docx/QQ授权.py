#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
import time
import uuid
import requests
import io
# 强制使用 UTF-8 编码
if sys.stdout.encoding != 'UTF-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
if sys.stderr.encoding != 'UTF-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 设置默认编码
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except:
        pass
DEFAULT_PROXY = "http://121.40.95.86"  # 默认代理IP

def main():
    # 1. 接收命令行参数
    parser = argparse.ArgumentParser(description='QQ OpenID 授权脚本（零交互版）')
    parser.add_argument('--openid', required=True, help='用户的 OpenID')
    parser.add_argument('--proxy', required=False, default=None, help='代理服务器地址')
    parser.add_argument('--device_id', required=False, help='设备ID')  # 添加设备ID参数
    args = parser.parse_args()
    openid = args.openid.strip()
    proxy = args.proxy or DEFAULT_PROXY  # 设置代理
    
    if not openid:
        print(json.dumps({"code":1, "message":"缺少 openid 参数"}, ensure_ascii=False))
        sys.exit(1)

    # 2. 使用传入的设备ID或生成新的
    device_id = args.device_id or uuid.uuid4().hex[:16]

    # 3. 构造请求参数（请根据实际接口文档确认字段）
    request_data = {
        "modelName":     "Xiaomi|2206122SC",            # 设备型号
        "appVersion":    "7.9.4",                      # APP 版本
        "buildVersion":  "25082611",                   # 构建版本
        "channel":       "other",                      # 渠道
        "thirdKey":      openid,                       # OpenID
        "appCode":       "SD001",                      # 应用 Code
        "thirdType":     "2",                          # 第三方类型
        "deviceId":      device_id,                    # 设备 ID
        "systemVersion": "12",                         # 系统版本
        "platform":      "2",                          # 平台（2=Android）
        "timestamp":     str(int(time.time() * 1000))  # 毫秒级时间戳
    }

    # 4. 生成签名（示例占位，生产请替换成真实签名算法）
    #    通常是对 request_data 按某种规则做哈希或 HMAC
    sign = "u2jqcsmPfIIE8T3UyVZFL6Puq+iOVCUNpAoRQOeyOHJDqveI2WKwXi66ArfEsWfOBo+WvbiEXsNMdotIg2hCJwqoZjGvgOIgdA7IzIqFjFA="

    # 5. 构造请求头
    headers = {
        "User-Agent":      "ShanDong/7.9.4 (Xiaomi;Android 12)",
        "sign":            sign,
        "Content-Type":    "application/json; charset=utf-8",
        "Host":            "api.huachenjie.com",
        "Connection":      "Keep-Alive",
        "Accept-Encoding": "gzip"
    }

    # 6. 发送请求
    url = "http://api.huachenjie.com/run-front/account/thirdLogin_v2"
    # 创建代理字典
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        response = requests.post(url, headers=headers, json=request_data, timeout=10,proxies=proxies)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(json.dumps({"code":1, "message":f"网络请求失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    # 7. 解析响应
    try:
        result = response.json()
    except ValueError:
        print(json.dumps({"code":1, "message":"响应不是合法 JSON", "raw": response.text}), ensure_ascii=False)
        sys.exit(1)

    # 8. 根据接口约定识别成功/失败，并输出统一格式
    if result.get("code") == 0:
        data = result.get("data", {})
        userId  = data.get("userId") or data.get("userID") or data.get("uid")
        token   = data.get("token")
        satoken = data.get("satoken")
        if userId and token and satoken:
        # 添加device_id到输出
         output_data = {
            "userId":  userId,
            "token":   token,
            "satoken": satoken,
            "device_id": device_id  # 使用传入或生成的设备ID
        }
        # 修改为直接输出JSON（移除调试信息）
        print(json.dumps({
            "code": 0,
            "data": output_data
        }, ensure_ascii=False))
        sys.exit(0)
    else:
        # 接口返回非零 code
        msg = result.get("message") or result.get("msg") or "未知错误"
        print(json.dumps({"code":1, "message":f"{msg}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()