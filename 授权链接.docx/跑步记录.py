import requests
import time
import hashlib
import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import sys
import io

# 强制使用 UTF-8 编码
if sys.stdout.encoding != 'UTF-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
if sys.stderr.encoding != 'UTF-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 设置默认编码
try:
    import locale
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except:
        pass

class SunRunClient:
    """跑步记录查询客户端（支持次数/距离两种完成方式）"""
    # 默认代理IP，与围栏脚本保持一致
    DEFAULT_PROXY = "http://121.40.95.86"
    
    def __init__(self, device_id, auth_token, satoken, proxy=None):
        """
        初始化客户端
        :param device_id: 设备指纹ID
        :param auth_token: 用户认证令牌
        :param satoken: 安全令牌
        """
        self.device_id = device_id
        self.auth_token = auth_token
        self.satoken = satoken
        self.run_plan_code = None
        self.proxy = proxy or self.DEFAULT_PROXY  # 设置代理
        
        # 固定参数
        self.base_url = "http://api.huachenjie.com/run-front"
        self.model_name = "Xiaomi|2206122SC"
        self.app_version = "7.6.8"
        self.build_version = "25052315"
        self.channel = "other"
        self.app_code = "SD001"
        self.system_version = "12"
        self.platform = "2"
        self.semester_code = None  # 新增：保存学期代码
        
        # 创建会话
        self.session = requests.Session()
        # 配置代理
        if self.proxy:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            print(f"✅ 已设置代理: {self.proxy}")
        else:
            print("ℹ️ 未使用代理")

    def get_run_plans(self):
        """获取所有激活的跑步计划列表（智能去重）"""
        # 尝试的学期代码列表：空字符串和1到20
        semester_codes = [""] + [str(i) for i in range(1, 21)]
        all_active_plans = []
        seen_plans = {}  # 用于去重，key: (plan_code, plan_name), value: 计划信息
        
        for semester_code in semester_codes:
            endpoint = "run/plan/selectList"
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
            
            print(f"📋 获取跑步计划列表（学期代码: {semester_code if semester_code else '空'}）...")
            response = self._send_request(endpoint, payload, special_api=True)
            
            if response.get('code') != 0:
                continue
                
            plan_list = response.get('data', {}).get('list', [])
            if not plan_list:
                continue
            
            # 查找激活的计划
            active_plans = [plan for plan in plan_list if plan.get('planStatus') == 1]
            
            for plan in active_plans:
                plan_code = plan.get('runPlanCode')
                plan_name = plan.get('runPlanName')
                plan_key = (plan_code, plan_name)
                
                # 如果已经见过这个计划，比较学期代码的优先级
                if plan_key in seen_plans:
                    existing_semester = seen_plans[plan_key]['semester_code']
                    current_semester = semester_code
                    
                    # 优先选择空学期代码，如果没有空学期代码，选择数字最小的学期代码
                    if existing_semester == "":
                        # 已存在的计划学期代码为空，保持现有计划
                        continue
                    elif current_semester == "":
                        # 当前计划学期代码为空，替换现有计划
                        seen_plans[plan_key] = {
                            'run_plan_code': plan_code,
                            'run_plan_name': plan_name,
                            'semester_code': current_semester,
                            'plan_status': plan.get('planStatus'),
                            'start_date': plan.get('startDate'),
                            'end_date': plan.get('endDate')
                        }
                    elif int(current_semester) < int(existing_semester):
                        # 当前学期代码数字更小，替换现有计划
                        seen_plans[plan_key] = {
                            'run_plan_code': plan_code,
                            'run_plan_name': plan_name,
                            'semester_code': current_semester,
                            'plan_status': plan.get('planStatus'),
                            'start_date': plan.get('startDate'),
                            'end_date': plan.get('endDate')
                        }
                    else:
                        # 保持现有计划
                        continue
                else:
                    # 新计划，添加到字典
                    seen_plans[plan_key] = {
                        'run_plan_code': plan_code,
                        'run_plan_name': plan_name,
                        'semester_code': semester_code,
                        'plan_status': plan.get('planStatus'),
                        'start_date': plan.get('startDate'),
                        'end_date': plan.get('endDate')
                    }
        
        # 将字典转换为列表
        all_active_plans = list(seen_plans.values())
        print(f"✅ 找到 {len(all_active_plans)} 个激活的跑步计划（已去重）")
        return all_active_plans

    def set_run_plan(self, run_plan_code, semester_code):
        """设置当前使用的跑步计划和学期代码"""
        self.run_plan_code = run_plan_code
        self.semester_code = semester_code
        print(f"✅ 已选择跑步计划: {run_plan_code} (学期代码: {semester_code})")

    def get_sun_run_summary(self):
        """获取跑步摘要信息（使用相同的学期代码）"""
        if not self.run_plan_code or self.semester_code is None:
            print("⚠️ 未设置跑步计划代码或学期代码")
            return None
            
        endpoint = "run/querySunRunAbstractInfoV2"
        payload = {
            "modelName": self.model_name,
            "runPlanCode": self.run_plan_code,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        # 只有当学期代码不为空时才添加到payload中
        if self.semester_code != "":
            payload["semesterCode"] = self.semester_code
        
        print(f"🔍 获取跑步摘要信息（学期代码: '{self.semester_code}'）...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取摘要失败: {response.get('message')}")
            return None
            
        return response.get('data', {})

    def get_sun_run_records(self, page_num=1, page_size=10):
        """获取跑步记录列表（使用相同的学期代码）"""
        if not self.run_plan_code or self.semester_code is None:
            print("⚠️ 未设置跑步计划代码或学期代码")
            return []
            
        endpoint = "run/pageSunRunRecord"
        payload = {
            "runPlanCode": self.run_plan_code,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "pageSize": str(page_size),
            "appCode": self.app_code,
            "pageNum": str(page_num),
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "modelName": self.model_name,
            "timestamp": str(int(time.time() * 1000))
        }
        
        # 只有当学期代码不为空时才添加到payload中
        if self.semester_code != "":
            payload["semesterCode"] = self.semester_code
        
        print(f"📋 获取跑步记录列表（学期代码: '{self.semester_code}'）...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取记录失败: {response.get('message')}")
            return []
            
        return response.get('data', {}).get('list', [])

    def get_school_rule(self):
        """获取学校规则信息（使用相同的学期代码）"""
        if not self.run_plan_code or self.semester_code is None:
            print("⚠️ 未设置跑步计划代码或学期代码")
            return {}
            
        endpoint = "run/querySunRunAbstractInfoV2"
        payload = {
            "modelName": self.model_name,
            "runPlanCode": self.run_plan_code,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        # 只有当学期代码不为空时才添加到payload中
        if self.semester_code != "":
            payload["semesterCode"] = self.semester_code
        
        print(f"📋 获取学校规则信息（学期代码: '{self.semester_code}'）...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取规则失败: {response.get('message')}")
            return {}
            
        data = response.get('data', {})
        school_rule = data.get('schoolDemandRule', {})
        student_info = data.get('studentDoneRuleInfo', {})
        
        return {
            "school_rule": school_rule,
            "student_info": student_info
        }

    def get_student_info(self):
        """获取学生基本信息（姓名、班级、学号）"""
        endpoint = "account/queryStudentCard"
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
        
        print("👤 获取学生基本信息...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取学生信息失败: {response.get('message')}")
            return {}
            
        data = response.get('data', {})
        
        # 解密学生信息
        try:
            student_info = {
                "name": self.clean_decrypted_text(self.decrypt_aes_cbc(data.get('userName', ''), '4634344230323832424541383335353700000000000000000000000000000000', '30313233344142434445463536373839')),
                "student_number": self.clean_decrypted_text(self.decrypt_aes_cbc(data.get('schoolInfo', {}).get('studentNumber', ''), '4634344230323832424541383335353700000000000000000000000000000000', '30313233344142434445463536373839')),
                "class_name": data.get('schoolInfo', {}).get('className', '')
            }
            return student_info
        except Exception as e:
            print(f"❌ 解密学生信息失败: {str(e)}")
            return {
                "name": data.get('userName', ''),
                "student_number": data.get('schoolInfo', {}).get('studentNumber', ''),
                "class_name": data.get('schoolInfo', {}).get('className', '')
            }

    @staticmethod
    def decrypt_aes_cbc(encrypted_text, key_hex, iv_hex):
        """AES CBC 解密"""
        try:
            # 将十六进制字符串转换为字节
            key = bytes.fromhex(key_hex)
            iv = bytes.fromhex(iv_hex)
            
            # Base64 解码
            encrypted_bytes = base64.b64decode(encrypted_text)
            
            # 创建 AES 解密器
            cipher = AES.new(key, AES.MODE_CBC, iv)
            
            # 解密
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            
            # 去除填充 - 使用 PKCS7 去除填充
            pad_len = decrypted_bytes[-1]
            if pad_len < 1 or pad_len > 16:
                # 如果不是有效的 PKCS7 填充，尝试去除零填充
                decrypted_bytes = decrypted_bytes.rstrip(b'\x00')
            else:
                # 去除 PKCS7 填充
                decrypted_bytes = decrypted_bytes[:-pad_len]
            
            # 转换为字符串
            decrypted_text = decrypted_bytes.decode('utf-8')
            
            return decrypted_text
        except Exception as e:
            print(f"解密失败: {str(e)}")
            return encrypted_text  # 如果解密失败，返回原文本

    @staticmethod
    def clean_decrypted_text(text):
        """清理解密后的文本，去除控制字符和填充字符"""
        if not text:
            return text
        
        # 直接去除末尾的 \u0007 字符
        while text.endswith('\x07'):
            text = text[:-1]
        
        return text

    def calculate_completion(self, summary):
        """计算距离完成度还差多少（支持次数/距离两种方式）"""
        if not summary:
            return None
            
        school_rule = summary.get('schoolDemandRule', {})
        student_info = summary.get('studentDoneRuleInfo', {})
        
        # 判断完成方式：次数或距离
        completion_type = "距离" if school_rule.get('totalDistance', 0) > 0 else "次数"
        
        if completion_type == "次数":
            # 按次数计算完成度
            total_required = school_rule.get('totalTimes', 0)
            done_value = student_info.get('doneTargetTimes', 0)
            unit = "次"
        else:
            # 按距离计算完成度
            total_required = school_rule.get('totalDistance', 0)
            done_value = student_info.get('doneDistance', 0)
            unit = "米"
        
        # 计算剩余值
        remaining_value = max(0, total_required - done_value)
        
        # 计算完成百分比
        completion_percent = (done_value / total_required * 100) if total_required > 0 else 0
        
        # 格式化距离值（如果是距离）
        if completion_type == "距离":
            formatted_total = f"{total_required / 1000:.1f}公里"
            formatted_done = f"{done_value / 1000:.1f}公里"
            formatted_remaining = f"{remaining_value / 1000:.1f}公里"
        else:
            formatted_total = f"{total_required}{unit}"
            formatted_done = f"{done_value}{unit}"
            formatted_remaining = f"{remaining_value}{unit}"
        
        return {
            "completion_type": completion_type,
            "total_required": total_required,
            "done_value": done_value,
            "remaining_value": remaining_value,
            "completion_percent": round(completion_percent, 1),
            "formatted_total": formatted_total,
            "formatted_done": formatted_done,
            "formatted_remaining": formatted_remaining,
            "unit": unit
        }

    def format_record_details(self, record):
        """格式化记录详情"""
        # 时间戳转换
        start_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                  time.localtime(int(record['startTime']) / 1000))
        end_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                time.localtime(int(record['endTime']) / 1000))
        
        # 计算配速（秒/公里 → 分钟/公里）
        pace_sec = record.get('pace', 0)
        pace_min = f"{pace_sec // 60}:{pace_sec % 60:02d}"
        
        # 计算持续时间（秒 → 分钟）
        duration_min = record.get('duration', 0) / 60
        
        # 格式化距离（米 → 公里）
        distance_km = record.get('distance', 0) / 1000
        
        return {
            "记录代码": record.get('runRecordCode', ''),
            "开始时间": start_time,
            "结束时间": end_time,
            "距离": f"{distance_km:.2f}公里",
            "配速": f"{pace_min}分钟/公里",
            "步数": record.get('totalStep', 0),
            "步频": f"{record.get('frequency', 0)}步/分钟",
            "消耗卡路里": f"{record.get('calorie', 0):,}",
            "持续时间": f"{duration_min:.1f}分钟",
            "状态": "有效" if record.get('sunRunRecordStatus') == 1 else "无效"
        }

    def _send_request(self, endpoint, payload, special_api=False):
        """发送API请求（复用签名逻辑）"""
        url = f"{self.base_url}/{endpoint}"
        
        headers = {
            "User-Agent": "ShanDong/7.6.8 (Xiaomi;Android 12)",
            "Authorization": f"Bearer {self.auth_token}",
            "satoken": self.satoken,
            "Content-Type": "application/json; charset=utf-8",
            "Host": "api.huachenjie.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        
        if special_api:
            api_module = endpoint.split('/')[0] if '/' in endpoint else endpoint
            headers.update({
                "app": "run-front",
                "e": "0",
                "v": endpoint.split('/')[-1] if '/' in endpoint else endpoint,
                "pv": "2",
                "api": api_module,
                "k": ""
            })
        
        # 生成签名
        try:
            json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            headers["sign"] = self.makesign(json_str)
        except Exception as e:
            print(f"❌ 签名生成失败: {str(e)}")
        
        try:
            response = self.session.post(
                url, 
                headers=headers, 
                json=payload, 
                timeout=15, 
                verify=False
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ 请求失败: HTTP {response.status_code}")
                print(f"响应内容: {response.text[:200]}")
                return {"code": -1, "message": f"HTTP错误: {response.status_code}"}
        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")
            return {"code": -1, "message": str(e)}
    
    @staticmethod
    def makesign(body):
        """生成请求签名（复用相同逻辑）"""
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

# 使用示例
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='跑步记录查询客户端')
    parser.add_argument('--device_id', required=True, help='设备ID')
    parser.add_argument('--auth_token', required=True, help='认证令牌')
    parser.add_argument('--satoken', required=True, help='安全令牌')
    parser.add_argument('--run_plan_code', required=False, help='跑步计划代码')
    parser.add_argument('--semester_code', required=False, help='学期代码')
    parser.add_argument('--proxy', required=False, default=None, help='代理服务器地址')
    args = parser.parse_args()
    
    try:
        # 初始化客户端
        client = SunRunClient(
            device_id=args.device_id,
            auth_token=args.auth_token,
            satoken=args.satoken,
            proxy=args.proxy
        )
        
        # 1. 获取所有跑步计划
        all_plans = client.get_run_plans()
        if not all_plans:
            raise RuntimeError("未找到任何激活的跑步计划")
        
        # 2. 如果指定了跑步计划代码，使用指定的计划
        if args.run_plan_code and args.semester_code:
            # 验证指定的计划是否存在
            plan_exists = any(
                plan['run_plan_code'] == args.run_plan_code and 
                plan['semester_code'] == args.semester_code 
                for plan in all_plans
            )
            
            if plan_exists:
                client.set_run_plan(args.run_plan_code, args.semester_code)
            else:
                print(f"⚠️ 指定的跑步计划不存在，使用第一个可用计划")
                first_plan = all_plans[0]
                client.set_run_plan(first_plan['run_plan_code'], first_plan['semester_code'])
        else:
            # 否则使用第一个计划（保持向后兼容）
            first_plan = all_plans[0]
            client.set_run_plan(first_plan['run_plan_code'], first_plan['semester_code'])
        
        # 3. 获取跑步摘要信息
        summary = client.get_sun_run_summary()
        completion = None
        if summary:
            completion = client.calculate_completion(summary)
        
        # 4. 获取学校规则信息
        rule_info = client.get_school_rule()
        
        # 5. 获取学生基本信息
        student_info = client.get_student_info()
        
        # 6. 获取跑步记录
        records = client.get_sun_run_records(page_size=10)
        formatted_records = []
        if records:
            for record in records:
                formatted_records.append(client.format_record_details(record))
        
        # 准备输出结果
        output = {
            "code": 0,
            "run_plan_code": client.run_plan_code,
            "semester_code": client.semester_code,
            "all_plans": all_plans,  # 返回所有计划列表
            "completion_type": completion["completion_type"] if completion else "未知",
            "formatted_total": completion["formatted_total"] if completion else "0",
            "formatted_done": completion["formatted_done"] if completion else "0",
            "formatted_remaining": completion["formatted_remaining"] if completion else "0",
            "completion_percent": completion["completion_percent"] if completion else 0,
            "school_rule": rule_info.get("school_rule", {}),
            "student_info": rule_info.get("student_info", {}),
            "student_basic_info": student_info,  # 新增：学生基本信息
            "records": formatted_records
        }
        
        # 输出JSON结果
        print(json.dumps(output, ensure_ascii=False))
        
    except Exception as e:
        print(json.dumps({"code": 1, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)