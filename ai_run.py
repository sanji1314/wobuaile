import requests
import time
import hashlib
import base64
import random
import os
import json
import uuid
import hmac
import sys
import traceback
import tempfile
import logging
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import ssl
import http.client
from datetime import datetime, timezone, timedelta
import urllib3
from urllib.parse import urlparse

def setup_logging():
    """配置日志记录，处理权限问题，返回日志文件路径"""
    try:
        main_log_dir = "/var/log/ai_exercise"
        if not os.path.exists(main_log_dir):
            os.makedirs(main_log_dir, exist_ok=True)
            os.chmod(main_log_dir, 0o755)
        
        main_log_file = os.path.join(main_log_dir, "ai_debug.log")
        
        if not os.path.exists(main_log_file):
            open(main_log_file, 'w').close()
            os.chmod(main_log_file, 0o644)
        
        with open(main_log_file, 'a') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 日志初始化成功\n")
        
        return main_log_file
        
    except PermissionError:
        print("⚠️ 无法写入主日志目录，使用备选方案")
        
        web_log_dir = "/var/www/html/run_logs"
        web_log_file = os.path.join(web_log_dir, "ai_debug.log")
        try:
            if not os.path.exists(web_log_dir):
                os.makedirs(web_log_dir, exist_ok=True)
            
            with open(web_log_file, 'a') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Web目录日志初始化\n")
            
            return web_log_file
        except Exception as e:
            print(f"⚠️ Web目录日志失败: {str(e)}")
            
            temp_log = os.path.join(tempfile.gettempdir(), "ai_exercise.log")
            with open(temp_log, 'a') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 临时文件日志初始化\n")
            
            return temp_log
    except Exception as e:
        print(f"❌ 日志初始化失败: {str(e)}")
        return os.path.join(tempfile.gettempdir(), "ai_exercise.log")
    
def setup_logger(log_path):
    """创建详细的日志记录器"""
    logger = logging.getLogger('AiExerciseClient')
    logger.setLevel(logging.DEBUG)
    
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class AiExerciseClient:
    """AI运动全流程自动化客户端（考虑成绩达标标准）"""
    def __init__(self, device_id, auth_token, satoken, face_image_path=None, proxy=None, 
             ai_plan_code=None, ai_config_code=None, semester_code=None):
        """
        初始化客户端
        :param device_id: 设备指纹ID
        :param auth_token: 用户认证令牌
        :param satoken: 安全令牌
        :param face_image_path: 动作图片路径
        :param proxy: 代理地址
        """
        # 基础配置
        self.device_id = device_id
        self.auth_token = auth_token
        self.satoken = satoken
        self.face_image_path = face_image_path
        self.proxy = proxy

        # 运动相关参数
        self.ai_plan_code = ai_plan_code
        self.ai_config_code = ai_config_code
        self.semester_code = semester_code
        self.ai_record_code = None
        self.oss_info = None
        self.action_groups = []
        self.selected_group = None  # 存储选中的组合详情
        self.selected_actions = []  # 存储选中的动作列表
        
        # 固定参数
        self.base_url = "http://api.huachenjie.com/run-front"
        self.model_name = "Xiaomi|2206122SC"
        self.app_version = "8.0.8"
        self.build_version = "25102118"
        self.channel = "other"
        self.app_code = "SD001"
        self.system_version = "12"
        self.platform = "2"
        self.timestamp = str(int(time.time() * 1000))

        # 确保人脸图片路径有效
        self.face_image_path = "/www/wwwroot/yangrun.xyz/1.png"
        
        # 获取日志记录器
        logger = logging.getLogger('AiExerciseClient')
        
        # 记录路径检查结果
        if not os.path.exists(self.face_image_path):
            logger.warning(f"⚠️ 警告: 人脸图片不存在: {self.face_image_path}")
            
            # 尝试默认路径
            default_path = "/www/wwwroot/yangrun.xyz/3.jpg"
            if os.path.exists(default_path):
                logger.info(f"✅ 使用默认人脸图片: {default_path}")
                self.face_image_path = default_path
            else:
                logger.error(f"❌ 默认路径也不存在: {default_path}")
        else:
            logger.info(f"✅ 人脸图片存在: {self.face_image_path}")

        # 添加独立的URL
        self.oss_token_url = "http://api.huachenjie.com/run-front/aliyun/oss/getToken"
        self.finish_exercise_url = "http://api.huachenjie.com/run-front/ai/finishExerciseV2"

        # 创建会话
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=10,
            pool_maxsize=10
        )
        self.session.mount('https://', adapter)
        
        # 设置代理
        if self.proxy:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            print(f"🔌 使用代理: {self.proxy}")
        
        # 禁用不安全的SSL警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def execute_full_flow(self):
        """执行完整AI运动流程"""
        try:
            print("=== 开始执行AI运动流程 ===")
            
            # 1. 如果指定了计划代码，则使用它
            if self.ai_plan_code:
                print(f"使用指定的AI计划代码: {self.ai_plan_code}")
            else:
                # 获取AI运动计划
                if not self.get_ai_plans():
                    print("❌ 无法获取AI运动计划")
                    return False, "无法获取AI运动计划"
            
            # 2. 如果指定了组合代码，则使用它
            if self.ai_config_code:
                print(f"使用指定的AI组合代码: {self.ai_config_code}")
                
                # 使用 get_ai_exercise_groups 方法获取组合详情
                if not self.get_ai_exercise_groups():
                    print("❌ 无法获取组合列表")
                    return False, "无法获取组合列表"
                    
                # 查找指定的组合
                found_group = None
                for group in self.action_groups:
                    if group.get('aiExerciseConfigCode') == self.ai_config_code:
                        found_group = group
                        break
                
                if not found_group:
                    print(f"❌ 未找到组合代码: {self.ai_config_code}")
                    return False, f"未找到组合代码: {self.ai_config_code}"
                    
                self.selected_group = found_group
                self.selected_actions = found_group.get('configActionList', [])
                print(f"✅ 找到组合: {found_group.get('configName')}")
            else:
                # 检查是否可以开始运动
                if not self.check_start_ai_exercise():
                    print("❌ 无法开始AI运动")
                    return False, "无法开始AI运动"
                
                # 获取运动组合列表
                if not self.get_ai_exercise_groups():
                    print("❌ 无法获取运动组合")
                    return False, "无法获取运动组合"
                
                # 选择符合条件的运动组合
                if not self.select_qualified_group():
                    print("❌ 无法找到符合条件的运动组合")
                    return False, "无法找到符合条件的运动组合"
        
            # 5. 开始运动
            if not self.start_ai_exercise():
                print("❌ 开始运动失败")
                return False, "开始运动失败"
            
            # 6. 获取OSS凭证
            if not self.get_oss_token():
                print("❌ 获取OSS凭证失败")
                return False, "获取OSS凭证失败"
            
            # 7. 执行并上传动作数据
            if not self.execute_and_upload_actions():
                print("❌ 动作执行失败")
                return False, "动作执行失败"
            
            # 8. 完成运动
            success, remark = self.finish_ai_exercise()
            
            # 9. 获取运动详情
            detail = self.get_exercise_detail()
            
            # 关键修复：根据实际达标状态返回结果
            if detail and detail.get('status') == 1:
                return True, remark
            else:
                return False, remark
        
        except Exception as e:
            error_msg = f"流程异常: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg

    def get_ai_plans(self):
        """获取AI运动计划列表"""
        endpoint = "ai/planOption"
        payload = {
            "semesterCode": self.semester_code,
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": self.timestamp
        }
        
        print("🔍 获取AI运动计划列表...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取计划失败: {response.get('message')}")
            return False
        
        plans = response.get('data', {}).get('planList', [])
        if not plans:
            print("⚠️ 未找到有效的运动计划")
            return False
        
        # 选择第一个运动计划
        self.ai_plan_code = plans[0].get('planCode')
        print(f"✅ 选择运动计划: {plans[0].get('planName')} (代码: {self.ai_plan_code})")
        return True

    def check_start_ai_exercise(self):
        """检查是否可以开始AI运动"""
        endpoint = "ai/checkStartAiExercise"
        payload = {
            "aiExercisePlanCode": self.ai_plan_code,
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": self.timestamp
        }
        
        print("🔍 检查是否可以开始AI运动...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 检查失败: {response.get('message')}")
            return False
        
        limit_flag = response.get('data', {}).get('limitFlag', True)
        if limit_flag:
            print("⚠️ 今日运动次数已达上限")
            return False
        
        print("✅ 可以开始AI运动")
        return True

    def get_ai_exercise_groups(self):
        """获取AI运动组合列表"""
        endpoint = "ai/aiExerciseGroupList"
        payload = {
            "aiExercisePlanCode": self.ai_plan_code,
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": self.timestamp
        }
        
        print("🔍 获取运动组合列表...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取组合失败: {response.get('message')}")
            return False
        
        self.action_groups = response.get('data', {}).get('groupList', [])
        if not self.action_groups:
            print("⚠️ 未找到有效的运动组合")
            return False
        
        print(f"✅ 获取到 {len(self.action_groups)} 个运动组合")
        return True

    def select_qualified_group(self):
        """选择符合条件的运动组合（考虑达标标准）"""
        # 过滤出有动作的组合
        valid_groups = [g for g in self.action_groups if g.get('configActionList')]
        
        if not valid_groups:
            print("⚠️ 所有组合都没有动作")
            return False
        
        # 优先选择动作数量适中的组合（避免过多或过少）
        action_counts = [len(g['configActionList']) for g in valid_groups]
        avg_count = sum(action_counts) / len(action_counts)
        
        # 选择动作数量接近平均值的组合
        self.selected_group = min(
            valid_groups, 
            key=lambda g: abs(len(g['configActionList']) - avg_count)
        )
        
        self.ai_config_code = self.selected_group.get('aiExerciseConfigCode')
        config_name = self.selected_group.get('configName')
        action_count = len(self.selected_group.get('configActionList', []))
        total_seconds = self.selected_group.get('secondTimesTotal', 0)
        
        print(f"🎯 选择组合: {config_name}")
        print(f"🔢 动作数量: {action_count}")
        print(f"⏱️ 总时长: {total_seconds}秒")
        print(f"🔑 组合代码: {self.ai_config_code}")
        
        # 存储选中的动作列表
        self.selected_actions = self.selected_group.get('configActionList', [])
        return True

    def start_ai_exercise(self):
        """开始AI运动"""
        endpoint = "ai/startAiExerciseV2"
        payload = {
            "aiExerciseConfigCode": self.ai_config_code,
            "aiExercisePlanCode": self.ai_plan_code,
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": self.timestamp
        }
        
        print("🏃 开始AI运动...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            error_msg = response.get('message', '未知错误')
            print(f"❌ 开始运动失败: {error_msg}")
            return False, error_msg
        
        self.ai_record_code = response.get('data', {}).get('aiExerciseRecordCode')
        if not self.ai_record_code:
            print("❌ 未获取到运动记录代码")
            return False, "未获取到运动记录代码"
        
        print(f"✅ 运动已开始，记录代码: {self.ai_record_code}")
        return True

    def get_oss_token(self):
        """获取OSS上传凭证（使用独立URL）"""
        payload = {
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": self.timestamp
        }
        
        print("🔑 获取OSS上传凭证...")
        # 使用独立的URL发送请求
        response = self._send_request_direct(
            self.oss_token_url, 
            payload, 
            api_module="aliyun"
        )
        
        if response.get('code') != 0:
            print(f"❌ 获取OSS凭证失败: {response.get('message')}")
            return False
        
        self.oss_info = response.get('data', {})
        print("✅ OSS凭证获取成功")
        return True

    def upload_to_oss(self, file_path):
        """上传文件到OSS"""
        logger = logging.getLogger('AiExerciseClient')
    
        logger.info(f"🔍 检查人脸图片路径: {self.face_image_path}")
        logger.info(f"🔍 文件是否存在: {os.path.exists(self.face_image_path)}")

        if not self.oss_info:
            logger.error("❌ 请先获取OSS凭证")
            return None
        
        if not os.path.exists(self.face_image_path):
            # 添加备用路径尝试
            default_path = "/www/wwwroot/yangrun.xyz/3.jpg"
            print(f"⚠️ 指定路径不存在，尝试默认路径: {default_path}")
            if os.path.exists(default_path):
                print(f"✅ 使用默认人脸图片: {default_path}")
                self.face_image_path = default_path
            else:
                print(f"❌ 默认路径也不存在: {default_path}")
                return None
        
        file_ext = os.path.splitext(self.face_image_path)[1].lower()
        if not file_ext:
            file_ext = ".jpg"
        logger.info(f"📄 文件扩展名: {file_ext}")
        
        # 准备上传参数
        upload_url = self.oss_info["domain"]
        access_key_id = self.oss_info["accessKeyId"]
        access_key_secret = self.oss_info["accessKeySecret"]
        security_token = self.oss_info["securityToken"]
        bucket_name = "sd-campus-badge"
        
        # 生成唯一文件名
        file_ext = os.path.splitext(file_path)[1].lower() or ".jpg"
        file_name = f"{self.oss_info['directory']}/ai_exercise_img/{uuid.uuid4()}{file_ext}"
        
        # 获取当前时间
        current_time = datetime.now(timezone.utc)
        gmt_format = '%a, %d %b %Y %H:%M:%S GMT'
        gmt_date = current_time.strftime(gmt_format)
        
        # 构建签名字符串
        canonicalized_resource = f"/{bucket_name}/{file_name}"
        canonicalized_headers = f"x-oss-security-token:{security_token}"
        
        string_to_sign = (
            f"PUT\n"
            f"\n"
            f"image/jpeg\n"
            f"{gmt_date}\n"
            f"{canonicalized_headers}\n"
            f"{canonicalized_resource}"
        )
        
        # 计算HMAC-SHA1签名
        h = hmac.new(
            access_key_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        signature = base64.b64encode(h.digest()).decode('utf-8')
        auth_header = f"OSS {access_key_id}:{signature}"
        
        # 读取文件内容
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        # 构建请求URL
        parsed_url = urlparse(upload_url)
        host = parsed_url.hostname
        path = f"/{file_name}"
        
        # 创建SSL上下文
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        try:
            # 建立连接
            conn = http.client.HTTPSConnection(host, context=context, timeout=30)
            
            # 构建请求头
            headers = {
                "Authorization": auth_header,
                "x-oss-security-token": security_token,
                "Content-Type": "image/jpeg",
                "Date": gmt_date,
                "Host": host,
                "Content-Length": str(len(file_content))
            }
            
            # 发送PUT请求
            conn.request("PUT", path, body=file_content, headers=headers)
            
            # 获取响应
            response = conn.getresponse()
            
            if response.status == 200:
                file_url = f"{upload_url}/{file_name}"
                print(f"✅ 文件上传成功: {file_url}")
                return file_url
            else:
                print(f"❌ 上传失败: HTTP {response.status}")
                print(f"响应: {response.read().decode()}")
                return None
        except Exception as e:
            print(f"❌ 上传过程中出错: {str(e)}")
            return None

    def execute_and_upload_actions(self):
        """执行并上传动作数据（优化间隔时间）"""
        if not self.selected_actions:
            print("⚠️ 该组合没有动作")
            return True
        
        print(f"🏋️ 开始执行 {len(self.selected_actions)} 个动作...")
        
        total_duration = self.selected_group.get('secondTimesTotal', 300)
        start_time = int(time.time() * 1000) - total_duration * 1000
        
        # 批量准备所有动作数据
        all_actions_data = []
        for i, action in enumerate(self.selected_actions):
            sport_type = action.get('sportType')
            required_duration = action.get('secondTimes', 30)
            required_frequency = action.get('frequency', 10)
            rest_time = action.get('restTime', 10)
            
            # 确保完成次数达到要求
            min_frequency = max(required_frequency, int(required_frequency * 1.05))
            max_frequency = int(required_frequency * 1.2)
            complete_count = random.randint(min_frequency, max_frequency)
            
            # 确保有效时长达到要求
            min_effective = max(required_duration, int(required_duration * 0.85))
            max_effective = required_duration
            effective_duration = random.randint(min_effective, max_effective)
            
            # 计算动作开始时间
            action_start_time = start_time + i * (required_duration + rest_time) * 1000
            
            # 准备动作数据
            action_data = {
                "sportType": sport_type,
                "startTime": action_start_time,
                "completeCount": complete_count,
                "effectiveDuration": effective_duration,
                "calorie": self.calculate_calorie(sport_type, complete_count),
                "duration": required_duration,
                "requireTime": required_frequency
            }
            all_actions_data.append(action_data)
        
        # 上传所有动作数据（优化间隔）
        for i, action_data in enumerate(all_actions_data):
            sport_type = action_data['sportType']
            
            # 上传图片到OSS（仅第一个动作上传）
            file_url = ""
            if i == 0 and self.face_image_path:
                file_url = self.upload_to_oss(self.face_image_path)
            
            # 上传动作数据（带重试机制）
            success = False
            retries = 3
            
            for attempt in range(retries):
                endpoint = "ai/uploadExerciseRecordAction"
                payload = {
                    "aiExerciseRecordCode": self.ai_record_code,
                    "uploadExerciseRecordRequest": action_data,
                    "fileUrl": file_url,
                    "systemVersion": self.system_version,
                    "modelName": self.model_name,
                    "platform": self.platform,
                    "deviceId": self.device_id,
                    "buildVersion": self.build_version,
                    "appVersion": self.app_version,
                    "appCode": self.app_code,
                    "timestamp": str(int(time.time() * 1000))
                }
                
                print(f"📤 上传动作 {i+1}/{len(all_actions_data)} 数据 (尝试 {attempt+1}/{retries})...")
                print(f"  类型: {self.get_sport_type_name(sport_type)}")
                print(f"  完成: {action_data['completeCount']}次/{action_data['effectiveDuration']}秒")
                
                response = self._send_request(endpoint, payload, special_api=True)
                
                if response.get('code') == 0:
                    print(f"✅ 动作 {i+1} 上传成功")
                    success = True
                    break
                elif response.get('code') == 1006:  # 手速太快错误
                    print(f"⚠️ 服务器限流: {response.get('message')}")
                    # 更短的退避策略
                    sleep_time = random.uniform(1.5, 2.5) * (2 ** attempt)
                    print(f"  等待 {sleep_time:.1f} 秒后重试...")
                    time.sleep(sleep_time)
                else:
                    print(f"⚠️ 动作 {i+1} 上传失败: {response.get('message')}")
                    break
            
            if not success:
                print(f"❌ 动作 {i+1} 上传失败，跳过此动作")
            
            # 更短的间隔（0.5-1.5秒）
            if i < len(all_actions_data) - 1:
                sleep_time = random.uniform(1.5, 2.5)
                time.sleep(sleep_time)
        
        return True

    def calculate_calorie(self, sport_type, count):
        """根据动作类型和次数计算卡路里（优化版）"""
        # 基于您的成功记录调整卡路里系数
        calorie_factors = {
            1: 700,  # 深蹲 (23次->16100卡)
            2: 200,  # 开合跳 (24次->4800卡)
            3: 150,  # 高抬腿 (110次->16500卡)
            4: 80    # 弓步跳 (43次->3440卡)
        }
        factor = calorie_factors.get(sport_type, 100)
        
        # 添加随机波动 (±10%)
        adjusted_factor = factor * random.uniform(0.9, 1.1)
        return int(adjusted_factor * count)

    def get_sport_type_name(self, sport_type):
        """获取运动类型名称"""
        types = {
            1: "深蹲",
            2: "开合跳",
            3: "高抬腿",
            4: "弓步跳"
        }
        return types.get(sport_type, f"未知类型({sport_type})")

    def finish_ai_exercise(self):
        """完成AI运动（使用独立URL）"""
        payload = {
            "aiExerciseRecordCode": self.ai_record_code,
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": str(int(time.time() * 1000))
        }
        
        print("🏁 完成AI运动...")
        # 使用独立的URL发送请求
        response = self._send_request_direct(
            self.finish_exercise_url, 
            payload, 
            api_module="ai"
        )
        
        # 添加详细的响应日志
        print(f"完成运动响应: {json.dumps(response, indent=2, ensure_ascii=False)}")
        
        if response.get('code') != 0:
            error_msg = response.get('message', '未知错误')
            print(f"❌ 完成运动失败: {error_msg}")
            # 返回错误信息，让外部处理回调
            return False, error_msg
        
        # 关键修复：正确解析状态值
        status = response.get('data', {}).get('status')
        reward = response.get('data', {}).get('rewardEnergyValue', 0)
        
        # 状态1表示成功完成
        if status == 1:  
            print(f"✅ AI运动成功完成! 获得能量值: {reward}")
            return True, "AI运动成功完成"
        else:
            error_msg = f"运动完成状态: {status}，未获得奖励"
            print(f"⚠️ {error_msg}")
            return False, error_msg

    def get_exercise_detail(self):
        """获取运动详情（用于调试）"""
        endpoint = "ai/detailRecord"
        payload = {
            "aiExerciseRecordCode": self.ai_record_code,
            "systemVersion": self.system_version,
            "modelName": self.model_name,
            "platform": self.platform,
            "deviceId": self.device_id,
            "buildVersion": self.build_version,
            "appVersion": self.app_version,
            "appCode": self.app_code,
            "timestamp": str(int(time.time() * 1000))
        }
        
        print("📊 获取运动详情...")
        response = self._send_request(endpoint, payload, special_api=True)
        
        if response.get('code') != 0:
            print(f"❌ 获取详情失败: {response.get('message')}")
            return None
        
        # 打印详细结果
        detail = response.get('data', {})
        status = detail.get('status', 0)
        
        print(f"🏆 运动状态: {'达标' if status == 1 else '未达标'}")
        print(f"⏱️ 总时长: {detail.get('exerciseTotalTime', 0)}秒")
        print(f"🔥 消耗卡路里: {detail.get('calorieTotal', 0)}")
        print(f"📈 达标率: {detail.get('rate', 0)*100}%")
        
        # 打印每个动作的详情
        for i, action in enumerate(detail.get('exerciseRecordDetailList', [])):
            is_completed = action.get('completeCount', 0) >= action.get('requireTime', 0)
            print(f"\n动作 #{i+1}:")
            print(f"  类型: {self.get_sport_type_name(action.get('sportType'))}")
            print(f"  完成次数: {action.get('completeCount')}/{action.get('requireTime')} {'✅' if is_completed else '❌'}")
            print(f"  有效时长: {action.get('effectiveDuration')}秒")
            print(f"  消耗卡路里: {action.get('calorie')}")
        
        return detail

    def _send_request(self, endpoint, payload, special_api=False):
        """发送API请求到基础URL"""
        url = f"{self.base_url}/{endpoint}"
        
        # 从endpoint提取API模块名（如"ai/xxx" -> "ai"）
        api_module = endpoint.split('/')[0] if '/' in endpoint else endpoint
        
        return self._send_request_direct(url, payload, api_module)

    def _send_request_direct(self, full_url, payload, api_module):
        """直接发送API请求到完整URL"""
        headers = {
            "User-Agent": "ShanDong/7.9.4 (Xiaomi;Android 12)",
            "Authorization": f"Bearer {self.auth_token}",
            "satoken": self.satoken,
            "Content-Type": "application/json; charset=utf-8",
            "Host": "api.huachenjie.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "app": "run-front",
            "e": "0",
            "v": api_module,
            "pv": "2",
            "api": api_module,
            "k": ""
        }
        
        # 生成签名
        try:
            json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            headers["sign"] = self.makesign(json_str)
        except Exception as e:
            print(f"❌ 签名生成失败: {str(e)}")
        
        try:
            response = self.session.post(
                full_url, 
                headers=headers, 
                json=payload, 
                timeout=15, 
                verify=False
            )
            
            # 解析响应
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ 请求失败: HTTP {response.status_code}")
                print(f"响应: {response.text}")
                return {"code": -1, "message": f"HTTP错误: {response.status_code}"}
        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")
            return {"code": -1, "message": str(e)}
    
    @staticmethod
    def makesign(body):
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
        
        # 4. 关键修改：直接使用十六进制字符串的ASCII字节
        raw_data = swapped_hash.encode("utf-8")
        raw_data_padded = pad(raw_data, AES.block_size)
        
        # 5. AES-CBC加密
        cipher = AES.new(padded_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(raw_data_padded)
        
        # 6. Base64编码
        sign = base64.b64encode(encrypted).decode("utf-8")
        return sign

def main_wrapper():
    # 初始化变量
    callback_url = "http://yangrun.xyz/update_order_status.php"
    orderid = None
    status = 3  # 默认状态为失败
    remark = ""
    log_path = ""

    try:
        # 设置日志
        log_path = setup_logging()
        logger = setup_logger(log_path)
        
        logger.info("===== AI运动脚本启动 =====")
        
        # 记录接收到的所有参数
        logger.info(f"命令行参数: {sys.argv}")
        
        # 检查参数 - 现在需要至少2个参数
        if len(sys.argv) < 3:
            error_msg = f"错误：参数不足，需要JSON参数和订单ID,实际收到 {len(sys.argv)-1} 个参数"
            logger.error(error_msg)
            print(error_msg)
            remark = error_msg
            status = 3
            sys.exit(1)
        
        # 获取订单ID
        orderid = sys.argv[2]
        logger.info(f"订单ID: {orderid}")
        
        # 解析JSON参数
        try:
            params = json.loads(sys.argv[1])
            logger.info("参数解析成功")
            logger.info(json.dumps(params, indent=2, ensure_ascii=False))
        except Exception as e:
            error_msg = f"参数解析失败: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            remark = error_msg
            status = 3
            sys.exit(1)
        
        # 创建客户端
        try:
            logger.info("创建AiExerciseClient实例...")
            client = AiExerciseClient(
                device_id=params['device_id'],
                auth_token=params['auth_token'],
                satoken=params['satoken'],
                face_image_path=params.get('face_image_path'),
                proxy=params.get('proxy', "http://121.40.95.86"),
                ai_plan_code=params.get('ai_plan_code'),
                ai_config_code=params.get('ai_group_code'),
                semester_code=params.get('semester_code')
            )
            logger.info("客户端创建成功")
        except Exception as e:
            error_msg = f"创建客户端失败: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            remark = error_msg
            status = 3
            sys.exit(1)
        
        # 执行AI运动
        try:
            logger.info("开始执行AI运动流程...")
            success, remark = client.execute_full_flow()
            
            if success:
                logger.info("AI运动执行成功")
                print("🎉 AI运动成功完成！")
                status = 1  # 成功状态
            else:
                logger.error(f"AI运动执行失败: {remark}")
                print(f"❌ AI运动失败: {remark}")
                status = 3  # 失败状态
                
                # 即使失败也获取详情
                client.get_exercise_detail()
        except Exception as e:
            error_msg = f"AI运动执行异常: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            remark = error_msg
            status = 3
    except Exception as e:
        error_msg = f"全局异常: {str(e)}"
        try:
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            remark = error_msg
        except:
            print(f"❌ 全局异常: {error_msg}")
            print(traceback.format_exc())
            remark = f"日志记录失败: {error_msg}"
        status = 3

    finally:
        # 确保无论成功还是失败，都尝试回调更新状态
        if orderid:
            try:
                callback_params = {
                    'orderid': orderid,
                    'status': status,
                    'remark': remark
                }
                
                logger.info(f"发送状态回调: {callback_params}")
                
                # 发送回调请求
                response = requests.get(callback_url, params=callback_params, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"回调成功: {response.text}")
                    
                    # 检查回调响应，确保状态更新正确
                    try:
                        callback_result = response.json()
                        if callback_result.get('code') == 1:
                            logger.info("状态更新成功")
                        else:
                            logger.error(f"状态更新失败: {callback_result.get('msg')}")
                    except:
                        logger.info("回调响应非JSON格式")
                else:
                    logger.error(f"回调失败: HTTP {response.status_code}, {response.text}")
            except Exception as e:
                error_msg = f"回调异常: {str(e)}"
                try:
                    logger.error(error_msg)
                    logger.error(traceback.format_exc())
                except:
                    print(f"❌ 回调异常: {error_msg}")

if __name__ == "__main__":
    main_wrapper()