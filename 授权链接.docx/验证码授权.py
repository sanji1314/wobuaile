#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
import time
import uuid
import requests
import re
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry  
import base64
import hashlib
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

class HuachenjieLogin:
    def __init__(self, device_id=None, state_dir="/tmp/huachenjie_states", proxy=None):
        """
        初始化登录客户端
        :param device_id: 设备ID（可选）
        :param state_dir: 状态存储目录
        """
        self.phone_number = None
        self.device_id = device_id or self.generate_device_id()
        self.proxy = proxy or DEFAULT_PROXY  # 设置代理
        self.base_url = "http://api.huachenjie.com/run-front"
        self.model_name = "Xiaomi|2206122SC"
        self.app_version = "7.9.4"
        self.build_version = "25082611"
        self.channel = "other"
        self.app_code = "SD001"
        self.system_version = "12"
        self.platform = "2"
        self.encrypted_phone = None
        self.ticket = None
        self.auth_token = None
        self.satoken = None
        self.user_id = None
        self.register_type = None
        self.state_dir = state_dir
        # 创建带重试机制的Session
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
         # 配置代理
        if self.proxy:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            print(f"✅ 已设置代理: {self.proxy}")
        else:
            print("ℹ️ 未使用代理")
        # 确保状态目录存在
        os.makedirs(self.state_dir, exist_ok=True)

    @staticmethod
    def generate_device_id():
        """生成随机的设备ID"""
        return str(uuid.uuid4().hex)[:16]

    def makesign(self, body):
        """生成请求签名"""
        # 1. 计算 SHA-256 哈希
        sha = hashlib.sha256()
        sha.update(body.encode('utf-8'))
        hex_hash = sha.hexdigest()
        
        # 2. 交换首尾8字节（16字符）
        swapped_hash = hex_hash[-8:] + hex_hash[8:-8] + hex_hash[:8]
        
        # 3. 构建32字节密钥
        original_key = "RHXL092CDOYTQJVP"
        key_bytes = original_key.encode("utf-8")
        padded_key = key_bytes.ljust(32, b"\x00")
        
        iv = b'01234ABCDEF56789'  # 16字节
        
        # 4. 使用十六进制字符串的ASCII字节
        raw_data = swapped_hash.encode("utf-8")
        raw_data_padded = pad(raw_data, AES.block_size)
        
        # 5. AES-CBC加密
        cipher = AES.new(padded_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(raw_data_padded)
        
        # 6. Base64编码
        sign = base64.b64encode(encrypted).decode("utf-8")
        return sign

    def send_request(self, endpoint, payload, api_module):
        """发送API请求"""
        url = f"{self.base_url}/{endpoint}"
        json_str = json.dumps(payload, separators=(',', ':'))
        
        headers = {
            "app": "run-front",
            "e": "1",
            "v": endpoint,
            "pv": "2",
            "User-Agent": "ShanDong/7.9.4 (Xiaomi;Android 12)",
            "sign": self.makesign(json_str),
            "api": api_module,
            "k": "",
            "Content-Type": "application/json; charset=utf-8",
            "Host": "api.huachenjie.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        with requests.Session() as session:
            # 设置连接池大小和超时
            session.mount('https://', HTTPAdapter(pool_connections=10, pool_maxsize=100))
        try:
            # 记录请求详情
            self.log_debug(f"发送请求到 {url}")
            self.log_debug(f"请求头: {json.dumps(headers, indent=2)}")
            self.log_debug(f"请求体: {json_str}")
            
           # 使用session替代直接requests.post
            response = self.session.post(
                url,
                headers=headers,
                data=json_str,
                timeout=(3, 10)  # 连接3秒，读取10秒超时
            )
            
            # 记录响应详情
            self.log_debug(f"响应状态码: {response.status_code}")
            self.log_debug(f"响应内容: {response.text}")
            
            if response.status_code == 200:
                return response.json()
            else:
                self.log_error(f"请求失败: HTTP {response.status_code}")
                return None
        except Exception as e:
            self.log_error(f"请求异常: {str(e)}")
            return None

    def log_debug(self, message):
        """记录调试信息"""
        print(f"[DEBUG] {message}", file=sys.stderr)

    def log_error(self, message):
        """记录错误信息"""
        print(f"[ERROR] {message}", file=sys.stderr)

    def get_state_file(self, phone):
        """获取状态文件路径"""
        safe_phone = re.sub(r'[^a-zA-Z0-9]', '_', phone)
        return os.path.join(self.state_dir, f"{safe_phone}_state.json")

    def save_state(self, phone):
        """保存当前状态"""
        state = {
            "device_id": self.device_id,
            "encrypted_phone": self.encrypted_phone,
            "ticket": self.ticket,
            "register_type": self.register_type
        }
        
        state_file = self.get_state_file(phone)
        with open(state_file, 'w') as f:
            json.dump(state, f)
            self.log_debug(f"状态保存到 {state_file}")
        
        return state_file

    def load_state(self, phone):
        """加载保存的状态"""
        state_file = self.get_state_file(phone)
        if not os.path.exists(state_file):
            self.log_debug(f"状态文件不存在: {state_file}")
            return False
        
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
                self.device_id = state.get("device_id", self.device_id)
                self.encrypted_phone = state.get("encrypted_phone")
                self.ticket = state.get("ticket")
                self.register_type = state.get("register_type", 0)
                
                self.log_debug(f"状态从 {state_file} 加载")
                return True
        except Exception as e:
            self.log_error(f"加载状态失败: {str(e)}")
            return False

    def login_check(self, phone):
        """第一步：登录检查，获取加密手机号"""
        self.phone_number = phone
        
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "loginName": self.phone_number,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        self.log_debug("进行登录检查...")
        response = self.send_request("auth/loginCheck", payload, "auth")
        
        if response and response.get("code") == 0:
            self.encrypted_phone = response["data"]["phone"]
            self.register_type = response["data"].get("registerType", 0)
            self.log_debug(f"登录检查成功，加密手机号: {self.encrypted_phone}")
            self.log_debug(f"注册类型: {self.register_type} (0表示验证码登录)")
            return True
        else:
            error_msg = response.get("message") if response else "未知错误"
            self.log_error(f"登录检查失败: {error_msg}")
            return False

    def get_auth_code(self, phone):
        """第二步：获取验证码"""
        if not self.login_check(phone):
            return False
        
        send_type = "1"  # 始终使用1表示短信验证码
        
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "phone": self.encrypted_phone,
            "sendType": send_type,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        self.log_debug("正在请求验证码...")
        response = self.send_request("account/getAuthCode", payload, "account")
        
        if response and response.get("code") == 0:
            self.ticket = response["data"]["ticket"]
            self.log_debug(f"验证码已发送，ticket: {self.ticket}")
            
            # 保存状态
            self.save_state(phone)
            return True
        else:
            error_msg = response.get("message") if response else "未知错误"
            self.log_error(f"获取验证码失败: {error_msg}")
            return False

    def login_with_code(self, phone, auth_code):
        """第三步：使用验证码登录"""
        # 加载之前的状态
        if not self.load_state(phone):
            self.log_error("无法加载之前的状态，请重新发送验证码")
            return False, None
        
        self.phone_number = phone
        
        login_endpoint = "account/login_v3"
        
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "authCode": auth_code,
            "ticket": self.ticket,
            "phone": self.encrypted_phone,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        self.log_debug(f"正在使用验证码登录 ({login_endpoint})...")
        response = self.send_request(login_endpoint, payload, "account")
        
        if response and response.get("code") == 0:
            data = response["data"]
            self.auth_token = data["token"]
            self.satoken = data["satoken"]
            self.user_id = data["userId"]
            
            # 检查是否有警告提示
            alert_tip = data.get("alertTip", {})
            if alert_tip:
                self.log_debug(f"服务器警告 - 标题: {alert_tip.get('title', '无')}")
                self.log_debug(f"服务器警告 - 内容: {alert_tip.get('content', '无')}")
            
            self.log_debug("登录成功！")
            
            # 清理状态文件
            try:
                state_file = self.get_state_file(phone)
                if os.path.exists(state_file):
                    os.remove(state_file)
                    self.log_debug(f"已清理状态文件: {state_file}")
            except Exception as e:
                self.log_error(f"清理状态文件失败: {str(e)}")
            
            return True, None
        else:
            error_code = response.get("code") if response else -1
            error_msg = response.get("message") if response else "未知错误"
            self.log_error(f"登录失败: 错误代码 {error_code} - {error_msg}")
            return False, error_code

    def send_code(self, phone):
        """发送验证码"""
        return self.get_auth_code(phone)

    def verify_code(self, phone, code: str):
        """验证验证码并登录"""
        # 清理验证码格式
        code = re.sub(r"\D", "", code)
        if len(code) != 4:
            raise ValueError("验证码格式错误，请输入4位数字")
            
        # 使用验证码登录
        success, error_code = self.login_with_code(phone, code)
        if not success:
            raise RuntimeError(f"验证码错误，错误代码: {error_code}")
        return success

    def verify_and_get_token(self, phone, code: str):
        """验证验证码并返回凭证"""
        # 验证验证码
        self.verify_code(phone, code)
        
        # 返回凭证信息
        return {
            "device_id": self.device_id,
            "user_id": self.user_id,
            "token": self.auth_token,
            "satoken": self.satoken
        }

# -------------- 脚本入口 --------------
def main():
    parser = argparse.ArgumentParser(description='华晨界APP短信授权脚本')
    parser.add_argument('--phone', required=True, help='手机号码')
    parser.add_argument('--code', required=False, help='短信验证码')
    parser.add_argument('--debug', action='store_true', help='启用详细调试日志')
    parser.add_argument('--proxy', required=False, default=None, help='代理服务器地址')
    parser.add_argument('--device_id', required=False, help='设备ID')  # 添加设备ID参数
    args = parser.parse_args()

    # 验证手机号格式
    if not re.match(r"^1[3-9]\d{9}$", args.phone):
        result = {"code": 1, "message": "手机号码格式不正确"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # 在服务器环境中，状态目录应该是可写的
    state_dir = "/tmp/huachenjie_states"
    
    # 确保状态目录存在
    os.makedirs(state_dir, exist_ok=True)
    client = HuachenjieLogin(device_id=args.device_id, state_dir=state_dir, proxy=args.proxy)

    # 如果只传了 --phone，就发送验证码
    if not args.code:
        try:
            success = client.send_code(args.phone)
            if success:
                result = {"code": 0, "message": "验证码已发送"}
            else:
                result = {"code": 2, "message": "验证码发送失败"}
            
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0 if success else 1)
        except Exception as e:
            result = {"code": 3, "message": f"发送失败: {str(e)}"}
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)

    # 如果同时传了 --phone 和 --code，就校验并返回凭证
    try:
        result = client.verify_and_get_token(args.phone, args.code)
        output = {
            "code": 0,
            "message": "登录成功",
            "data": result
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)
    except Exception as e:
        result = {"code": 4, "message": f"校验失败: {str(e)}"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()