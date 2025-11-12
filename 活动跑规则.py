import hashlib
import time
import requests
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64

# 配置信息
modelName = "Xiaomi|2206122SC"
appVersion = "8.0.5"
buildVersion = "25101617"
deviceId = "dd1c8306fcb8470a"
systemVersion = "12"
Authorization = "eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjI0MTAwODE4MjQxNTkxOTY4LCJleHAiOjE3NjYzMzI4MDAsInBob25lIjoiMTMwODcwNjc3MDIiLCJpYXQiOjE3NjExOTEwMzF9.P5_oHP0sgIc9eAQPP8nKVpjhXQprOYLSxYkvYFaHboY"
satoken = "0d19b606-c689-48c8-98eb-70103aedfb22"
UA = "ShanDong/8.0.5 (Xiaomi;Android 12)"
appCode = "SD001"
channel = "xiaomi"
platform = "2"

BASE_URL = "http://api.huachenjie.com"

# 代理设置
proxy = "http://121.40.95.86"  # 使用与阳光跑相同的代理

def makesign(body):
    """生成签名 - 与阳光跑脚本相同的算法"""
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

    iv = b'01234ABCDEF56789'

    # 4. 准备数据
    raw_data = swapped_hash.encode("utf-8")
    raw_data_padded = pad(raw_data, AES.block_size)

    # 5. AES-CBC加密
    cipher = AES.new(padded_key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(raw_data_padded)

    # 6. Base64编码
    sign = base64.b64encode(encrypted).decode("utf-8")
    return sign

def send_post_request(url, body, extra_headers=None):
    """发送POST请求 - 与阳光跑脚本相同的实现"""
    headers = {
        "Authorization": Authorization,
        "satoken": satoken,
        "User-Agent": UA,
        "Content-Type": "application/json;charset=UTF-8",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    
    # 添加额外头部
    if extra_headers:
        headers.update(extra_headers)
    
    # 生成签名
    json_str = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    headers["sign"] = makesign(json_str)
    
    # 配置代理
    session = requests.Session()
    if proxy:
        session.proxies = {
            "http": proxy,
            "https": proxy
        }
    
    try:
        response = session.post(
            url=url,
            data=json_str.encode('utf-8'),
            headers=headers,
            timeout=10
        )
        return response
    except requests.exceptions.RequestException:
        return None

def get_activity_list():
    """获取活动跑列表"""
    url = BASE_URL + "/run-front/activity/activityList"
    timestamp = str(int(time.time() * 1000))
    
    body = {
        "modelName": modelName,
        "currentSemester": "true",
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "channel": channel,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "timestamp": timestamp
    }
    
    extra_headers = {
        "app": "run-front",
        "e": "0",
        "v": "activityList",
        "pv": "2",
        "api": "activity",
        "k": ""
    }
    
    response = send_post_request(url, body, extra_headers)
    if response and response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            return data.get("data", {})
    return None

def get_activity_detail(activity_code):
    """获取活动跑详情"""
    url = BASE_URL + "/run-front/activity/activityDetail"
    timestamp = str(int(time.time() * 1000))
    
    body = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "sunRunActivityCode": activity_code,
        "channel": channel,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "timestamp": timestamp
    }
    
    extra_headers = {
        "app": "run-front",
        "e": "0",
        "v": "activityDetail",
        "pv": "2",
        "api": "activity",
        "k": ""
    }
    
    response = send_post_request(url, body, extra_headers)
    if response and response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            return data.get("data", {})
    return None

def print_activity_rules(activity):
    """打印活动规则"""
    print(f"活动名称: {activity.get('activityName')}")
    print(f"活动代码: {activity.get('sunRunActivityCode')}")
    
    status_map = {0: "未开始", 1: "进行中", 2: "已结束", 3: "已暂停"}
    status = activity.get('activityStatus', 0)
    print(f"状态: {status_map.get(status, '未知')}")
    
    print(f"时间: {activity.get('startTime', '')} 至 {activity.get('endTime', '')}")
    
    rules = activity.get('activityRuleList', [])
    if rules:
        print("活动规则:")
        for rule in rules:
            rule_type = rule.get('ruleType')
            rule_value = rule.get('ruleValue')
            if rule_type == 1:
                print(f"  - 距离要求: {rule_value}米")
            elif rule_type == 2:
                print(f"  - 配速要求: {rule_value}分钟/公里")
            elif rule_type == 3:
                print(f"  - 步频要求: {rule_value}步/分钟")
            elif rule.get('ruleDesc'):
                print(f"  - {rule.get('ruleDesc')}")

def main():
    """主函数"""
    print("正在获取活动跑规则...")
    
    # 获取活动列表
    activity_data = get_activity_list()
    if not activity_data:
        print("获取活动列表失败")
        return
    
    activity_list = activity_data.get("activityList", [])
    if not activity_list:
        print("暂无活动")
        return
    
    print(f"找到 {len(activity_list)} 个活动")
    print("-" * 40)
    
    # 显示每个活动的规则
    for i, activity in enumerate(activity_list, 1):
        print(f"\n活动{i}:")
        print_activity_rules(activity)
        
        # 获取详细规则
        activity_code = activity.get('sunRunActivityCode')
        if activity_code:
            detail = get_activity_detail(activity_code)
            if detail:
                print_activity_rules(detail)
        
        print("-" * 40)

if __name__ == "__main__":
    main()