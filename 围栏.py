import requests
import json
import time
import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import sys
import os
import logging
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
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

class SchoolInfoFetcher:
    """学校信息获取工具（包含学校代码和围栏信息）"""
    # 默认代理IP，与Sunshine脚本保持一致
    DEFAULT_PROXY = "http://121.40.95.86"
    
    def __init__(self, device_id, auth_token, satoken, proxy=None):
        """
        初始化客户端
        :param device_id: 设备指纹ID
        :param auth_token: 用户认证令牌
        :param satoken: 安全令牌
        """
        # 基础配置
        self.device_id = device_id
        self.auth_token = auth_token
        self.satoken = satoken
        # 设置代理 - 与Sunshine脚本相同的逻辑
        self.proxy = proxy or self.DEFAULT_PROXY
        
        # 固定参数
        self.model_name = "Xiaomi|2206122SC"
        self.app_version = "7.6.8"
        self.build_version = "25052315"
        self.channel = "other"
        self.app_code = "SD001"
        self.system_version = "12"
        self.platform = "2"
        
        # 创建会话
        self.session = requests.Session()
        # 配置代理 - 不再打印到 stdout
        if self.proxy:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
    
    @staticmethod
    def makesign(body):
        """正确的签名生成方法"""
        # 1. 计算 SHA-256 哈希
        sha = hashlib.sha256()
        sha.update(body.encode('utf-8'))
        hex_hash = sha.hexdigest()  # 64字符的十六进制字符串
        
        # 2. 交换首尾8字节（16字符）
        swapped_hash = hex_hash[-8:] + hex_hash[8:-8] + hex_hash[:8]
        
        # 3. 构建32字节密钥（注意O改为0，并补16个\x00）
        original_key = "RHXL092CDOYTQJVP"
        key_bytes = original_key.encode("utf-8")
        padded_key = key_bytes.ljust(32, b"\x00")
        
        iv = b'01234ABCDEF56789'  # 16字节
        
        # 4. 关键修改：直接使用十六进制字符串的ASCII字节
        raw_data = swapped_hash.encode("utf-8")
        raw_data_padded = pad(raw_data, AES.block_size)
        
        # 5. AES-CBC加密
        cipher = AES.new(padded_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(raw_data_padded)
        
        # 6. Base64编码
        sign = base64.b64encode(encrypted).decode("utf-8")
        return sign
    
    def _send_request(self, endpoint, payload, api_module, api_version):
        """统一请求方法"""
        url = f"http://api.huachenjie.com/run-front/{endpoint}"
        
        # 构建headers
        headers = {
            "app": "run-front",
            "Authorization": f"Bearer {self.auth_token}",
            "satoken": self.satoken,
            "e": "0",
            "v": api_version,
            "pv": "2",
            "User-Agent": "ShanDong/7.6.8 (Xiaomi;Android 12)",
            "api": api_module,
            "k": "",
            "Content-Type": "application/json; charset=utf-8",
            "Host": "api.huachenjie.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        
        # 生成签名
        json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        headers["sign"] = self.makesign(json_str)
        
        # 发送请求
        try:
            response = self.session.post(
                url,
                headers=headers,
                json=payload,
                timeout=15,
                verify=False
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            return None
    
    def get_run_plans(self, semester_code=""):
        """获取跑步计划列表（包含学校代码），支持指定学期代码"""
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "semesterCode": semester_code,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        response = self._send_request(
            "run/plan/selectList",
            payload,
            api_module="run",
            api_version="plan"
        )
        
        if not response:
            return None
        
        if response.get("code") != 0:
            return None
        
        return response.get("data", {})
    
    def find_active_run_plan(self):
        """遍历学期代码查找激活的跑步计划"""
        # 先尝试空学期代码
        school_info = self.get_run_plans()
        if school_info and school_info.get("list"):
            for plan in school_info.get("list", []):
                if plan.get("planStatus") == 1:
                    return school_info
        
        # 遍历1-20的学期代码
        for i in range(1, 21):
            school_info = self.get_run_plans(str(i))
            if school_info and school_info.get("list"):
                for plan in school_info.get("list", []):
                    if plan.get("planStatus") == 1:
                        return school_info
            time.sleep(0.3)  # 避免请求过快
        
        return None
    
    def get_school_fences(self, school_code):
        """获取学校围栏信息"""
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "schoolCode": school_code,
            "timestamp": str(int(time.time() * 1000))
        }
        
        response = self._send_request(
            "school/querySchoolFences",
            payload,
            api_module="school",
            api_version="querySchoolFences"
        )
        
        if not response:
            return None
        
        if response.get("code") != 0:
            return None
        
        return response.get("data", [])
    
    def get_school_name(self):
        """获取学校名称"""
        endpoint = "mySchool/simpleInfo"
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        response = self._send_request(
            endpoint,
            payload,
            api_module="mySchool",
            api_version="simpleInfo"
        )
        
        if not response or response.get("code") != 0:
            return None
        
        # 从响应中提取学校名称
        official_channel = response.get("data", {}).get("officialChannel", {})
        return official_channel.get("channelName")


# 使用示例
# 新增：命令行接口
if __name__ == "__main__":
    # 禁用所有日志输出到 stdout
    logging.disable(logging.CRITICAL)
    
    try:
        # 检查参数数量
        if len(sys.argv) < 2:
            print(json.dumps({"error": "参数不足，需要设备ID、认证令牌和安全令牌"}))
            exit(1)
        
        # 尝试解析第一个参数为JSON
        try:
            params = json.loads(sys.argv[1])
            device_id = params.get('device_id')
            auth_token = params.get('auth_token')
            satoken = params.get('satoken')
            proxy = params.get('proxy')
            
            if not device_id or not auth_token or not satoken:
                raise ValueError("JSON中缺少必要字段")
        except:
            # 如果解析失败，则尝试使用传统参数格式
            if len(sys.argv) < 4:
                print(json.dumps({"error": "参数不足，需要设备ID、认证令牌和安全令牌"}))
                exit(1)
            
            device_id = sys.argv[1]
            auth_token = sys.argv[2]
            satoken = sys.argv[3]
            proxy = sys.argv[4] if len(sys.argv) >= 5 else None
        
        # 创建信息获取器
        fetcher = SchoolInfoFetcher(device_id, auth_token, satoken, proxy)
        
        # 获取跑步计划 - 使用新的遍历方法
        school_info = fetcher.find_active_run_plan()
        if not school_info:
            print(json.dumps({"error": "获取跑步计划失败，未找到激活的计划"}))
            exit(1)
        
        # 准备跑步计划数据
        plans = []
        for plan in school_info.get("list", []):
            plans.append({
                "runPlanCode": plan.get("runPlanCode"),
                "runPlanName": plan.get("runPlanName")
            })
        
        # 获取学校名称
        school_name = fetcher.get_school_name()
        
        # 准备围栏数据
        fences = []
        school_code = school_info.get("schoolCode")
        if school_code:
            fence_list = fetcher.get_school_fences(school_code)
            if fence_list:
                for fence in fence_list:
                    fences.append({
                        "fenceCode": fence.get("fenceCode"),
                        "fenceName": fence.get("fenceName"),
                        "subSchoolName": fence.get("subSchoolName"),
                        "schoolName": school_name  # 添加学校名称
                    })
        
        # 输出JSON结果
        result = {
            "plans": plans,
            "fences": fences,
            "schoolName": school_name
        }
        print(json.dumps(result, ensure_ascii=False))
        
    except Exception as e:
        # 确保异常时也只输出JSON
        print(json.dumps({"error": str(e)}))
        exit(1)