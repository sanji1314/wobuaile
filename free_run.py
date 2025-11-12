import requests
import time
import hashlib
import base64
import random
import os
import json
import math
import uuid
import hmac
import numpy as np
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import logging
import socket
from datetime import datetime, timezone
from requests.adapters import HTTPAdapter
import xml.etree.ElementTree as ET
import ssl
import http.client
from datetime import datetime, timezone, timedelta
import urllib3
from urllib.parse import urlparse, quote
import sys
import traceback
import tempfile

# 添加日志配置函数
def setup_logging():
    """配置日志记录，处理权限问题，返回日志文件路径"""
    try:
        main_log_dir = "/var/log/sunrun"
        if not os.path.exists(main_log_dir):
            os.makedirs(main_log_dir, exist_ok=True)
            os.chmod(main_log_dir, 0o755)
        
        main_log_file = os.path.join(main_log_dir, "freerun_debug.log")
        
        if not os.path.exists(main_log_file):
            open(main_log_file, 'w').close()
            os.chmod(main_log_file, 0o644)
        
        with open(main_log_file, 'a') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 自由跑日志初始化成功\n")
        
        return main_log_file
        
    except PermissionError:
        print("⚠️ 无法写入主日志目录，使用备选方案")
        
        web_log_dir = "/var/www/html/run_logs"
        web_log_file = os.path.join(web_log_dir, "freerun_debug.log")
        try:
            if not os.path.exists(web_log_dir):
                os.makedirs(web_log_dir, exist_ok=True)
            
            with open(web_log_file, 'a') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Web目录日志初始化\n")
            
            return web_log_file
        except Exception as e:
            print(f"⚠️ Web目录日志失败: {str(e)}")
            
            temp_log = os.path.join(tempfile.gettempdir(), "yangrun_freerun_python.log")
            with open(temp_log, 'a') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 临时文件日志初始化\n")
            
            return temp_log
    except Exception as e:
        print(f"❌ 日志初始化失败: {str(e)}")
        return os.path.join(tempfile.gettempdir(), "yangrun_freerun_python.log")
    
def setup_logger(log_path):
    """创建详细的日志记录器"""
    logger = logging.getLogger('FreeRunClient')
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

class FreeRunClient:
    def __init__(self, device_id, auth_token, satoken, distance, total_step, duration, 
                 face_image_path=None, proxy=None, trajectory_points=None):
        self.device_id = device_id
        self.auth_token = auth_token
        self.satoken = satoken
        self.face_image_path = face_image_path
        self.proxy = proxy

        self.distance = int(distance)
        self.total_step = int(total_step)
        self.duration = int(duration)
        self.start_location = None
        
        self.base_url = "http://api.huachenjie.com/run-front/run"
        self.max_retries = 5
        self.retry_delay = 5
        
        self.run_record_code = None
        self.timestamp = str(int(time.time() * 1000))
        self.trajectory_index = 0
        self.run_start_time = 0
        self.global_index_counter = 0
        self.stride_index_counter = 0
        self.trajectory_points = trajectory_points or []
        print(f"📊 轨迹点数量: {len(self.trajectory_points)}")

        self.auth_expired = False
        self.last_error_code = 0
        self.auth_error_codes = [1503, 1516]
        
        self.session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=5,
            pool_connections=100,
            pool_maxsize=100
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.model_name = "Xiaomi|2206122SC"
        self.app_version = "8.1.8"
        self.build_version = "25103117"
        self.channel = "other"
        self.app_code = "SD001"
        self.system_version = "12"
        self.platform = "2"

        # 步数和配速记录
        self.all_step_records = []
        self.all_pace_records = []
        
        # 修复代理端口配置
        if self.proxy:
            # 确保代理地址包含端口号
            if "://" in self.proxy and ":" not in self.proxy.split("//")[1]:
                self.proxy += ":80"
            
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }
            print(f"🔌 使用代理: {self.proxy}")

        if isinstance(trajectory_points, str):
            try:
                self.trajectory_points = json.loads(trajectory_points)
                print(f"✅ 解析轨迹点数据: {len(self.trajectory_points)}个点")
            except json.JSONDecodeError:
                print("❌ 轨迹点数据解析失败，使用空列表")
                self.trajectory_points = []
        else:
            self.trajectory_points = trajectory_points or []
            
        print(f"📊 轨迹点数量: {len(self.trajectory_points)}")
            
    def run_free_run(self):
        """执行自由跑流程"""
        try:
            print("\n=== 开始执行自由跑 ===")
            self.start_free_run()
            self.upload_run_data()
            self.simulate_running()
            success = self.finish_free_run()
            
            if success:
                print("✅✅✅ 自由跑执行成功 ✅✅✅")
            else:
                print("❌ 自由跑执行失败")
            
            return success
        except StartRunError as e:
            if e.code == 1006:
                print(f"❌ 1006错误: {e.message}")
                return self.handle_1006_error(e.response)
            else:
                print(f"❌ 启动失败({e.code}): {e.message}")
                return False
        except Exception as e:
            print(f"❌ 流程异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def start_free_run(self):
        """启动自由跑"""
        self.run_start_time = int(time.time() * 1000)
        self.trajectory_index = 0
        self.global_index_counter = random.randint(500, 1000)
        self.stride_index_counter = 0

        # 设置起始位置为第一个轨迹点
        if self.trajectory_points and len(self.trajectory_points) > 0:
            if isinstance(self.trajectory_points[0], (list, tuple)):
                self.start_location = (self.trajectory_points[0][0], self.trajectory_points[0][1])
            elif isinstance(self.trajectory_points[0], dict):
                self.start_location = (self.trajectory_points[0]['lng'], self.trajectory_points[0]['lat'])
            else:
                # 默认位置
                self.start_location = (120.523568, 30.647431)
        else:
            # 默认位置
            self.start_location = (120.523568, 30.647431)
        
        lng, lat = self.start_location
        
        payload = {
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "lng": lng,
            "channel": self.channel,
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "lat": lat,
            "platform": self.platform,
            "timestamp": self.timestamp
        }
        
        print("🏃 开始自由跑...")
        response = self._send_request(
            "startFreeRun",
            payload,
            special_api=True,
            api_module="run",
            api_version="startFreeRun"
        )
        
        if response.get('code') != 0:
            error_code = response.get('code', 1006)
            error_msg = response.get('message', '未知错误')
            raise StartRunError(error_code, error_msg, response)
       
        if 'data' not in response:
            raise StartRunError(1005, "响应中缺少data字段", response)
       
        data = response['data']
       
        if 'runRecordCode' in data:
            self.run_record_code = data['runRecordCode']
            print(f"✅ 成功获取RunRecordCode: {self.run_record_code}")
        else:
            print(f"❌ 响应中缺少runRecordCode字段: {response}")
            raise StartRunError(1005, "响应中缺少runRecordCode字段", response)
       
        print(f"📊 初始化全局索引计数器: {self.global_index_counter}")
        print(f"📊 初始化步幅索引计数器: {self.stride_index_counter}")
        return True
 
    def upload_run_data(self):
        logger = logging.getLogger('FreeRunClient')
        
        # 生成轨迹点
        gps_points = self._generate_gps_points()
        
        # 验证轨迹
        if not self.validate_trajectory(gps_points, min_distance=300):
            logger.warning("⚠️ 轨迹验证失败，但继续使用原始轨迹点")
        
        payload = {
            "pois": gps_points,
            "runRecordCode": self.run_record_code,
            "deviceId": self.device_id,
            "timestamp": str(int(time.time() * 1000)),
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "systemVersion": "12",
            "platform": "2"
        }
        
        logger.info(f"📡 上传自由跑数据，包含 {len(gps_points)} 个轨迹点")
        response = self._send_request('uploadRunRecord', payload)
        logger.info("✅ 自由跑数据上传完成")
        return response

    def simulate_running(self):
        """模拟跑步过程数据上报"""
        # 1. 生成覆盖所有点的GPS轨迹
        self.upload_run_data()
        
        # 2. 计算跑步过程中的数据上报次数
        # 步幅：每100-150米上传一次
        stride_upload_count = max(1, int(self.distance / random.randint(100, 150)))
        # 步数：每20-30秒上传一次
        step_upload_count = max(1, int(self.duration / random.randint(20, 30)))
        # 配速：每30-40秒上传一次
        pace_upload_count = max(1, int(self.duration / random.randint(30, 40)))
        
        print(f"📊 跑步数据上传计划: 步幅={stride_upload_count}次, 步数={step_upload_count}次, 配速={pace_upload_count}次")
        
        # 3. 模拟跑步过程中多次上报数据
        for i in range(step_upload_count):
            step_indices = self.upload_step_data()
            print(f"📊 步数数据上传 | 索引: {step_indices}")
            time.sleep(random.uniform(0.5, 1.5))
            
            # 每2次步数上传后上传1次配速
            if i % 2 == 0 and i < pace_upload_count:
                pace_indices = self.upload_pace_data()
                print(f"📊 配速数据上传 | 索引: {pace_indices}")
                time.sleep(random.uniform(0.5, 1.5))
        
        # 上传步幅数据
        for i in range(stride_upload_count):
            stride_indices = self.upload_stride_data()
            print(f"📊 步幅数据上传 | 索引: {stride_indices}")
            time.sleep(random.uniform(0.5, 1.5))
            
            # 每3次步幅上传后上传1次配速
            if i % 3 == 0 and i < pace_upload_count:
                pace_indices = self.upload_pace_data()
                print(f"📊 补充配速上传 | 索引: {pace_indices}")
                time.sleep(random.uniform(0.5, 1.5))
        
        print("✅ 跑步过程模拟完成")
        
    def finish_free_run(self):
        """结束自由跑"""
        url = "http://api.huachenjie.com/run-front/run/finishFreeRun"
        
        # 获取最后几个轨迹点
        pois = self.get_realistic_pois()
        
        payload = {
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "stepInterval": 20,
            "distance": str(self.distance),
            "totalStep": str(self.total_step),
            "channel": self.channel,
            "stepList": self.all_step_records[-3:] if self.all_step_records else self._generate_step_records(1),
            "appCode": self.app_code,
            "deviceId": self.device_id,
            "systemVersion": self.system_version,
            "platform": self.platform,
            "runRecordCode": self.run_record_code,
            "duration": str(self.duration),
            "modelName": self.model_name,
            "paceList": self.all_pace_records[-3:] if self.all_pace_records else self._generate_pace_segments(1),
            "paceInterval": 50,
            "pois": pois,
            "timestamp": str(int(time.time() * 1000))
        }
        
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "satoken": self.satoken,
            "User-Agent": "ShanDong/7.9.4 (Xiaomi;Android 12)",
            "Content-Type": "application/json; charset=utf-8",
            "Host": "api.huachenjie.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        
        headers["sign"] = self.generate_sign(payload)
        
        print("🏁 提交结束自由跑请求...")
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=10)
            
            print(f"📡 状态码: {response.status_code}")
            if response.text:
                try:
                    resp_data = response.json()
                    print(f"📡 响应文本: {json.dumps(resp_data, indent=2, ensure_ascii=False)}")
                except:
                    print(f"📡 响应文本: {response.text}")
            else:
                print("📡 响应文本: (空)")
            
            if response.status_code == 200:
                data = response.json()
                code = data.get("code")
                if code == 0:
                    print("✅ 自由跑成功结束")
                    return True
                else:
                    print(f"❌ 结束自由跑失败: {data.get('message')}")
            else:
                print(f"❌ 请求失败: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")
        
        return False

    def _generate_gps_points(self):
        """生成GPS点，使用前端传递的轨迹点"""
        logger = logging.getLogger('FreeRunClient')
        
        # 使用前端传递的轨迹点
        if self.trajectory_points and len(self.trajectory_points) >= 2:
            logger.info("📍 使用前端传递的轨迹点生成轨迹")
            base_time = self.run_start_time
            points = []
            current_index = self.trajectory_index
            
            # 计算总距离
            total_distance = 0
            for i in range(1, len(self.trajectory_points)):
                segment_distance = self._calculate_distance(
                    self.trajectory_points[i-1], 
                    self.trajectory_points[i]
                )
                total_distance += segment_distance
            
            # 计算需要的额外距离
            extra_distance = max(0, self.distance - total_distance)
            
            # 计算平均速度 (m/s)
            avg_speed = self.distance / self.duration if self.duration > 0 else 2.5
            
            # 生成时间序列
            accumulated_time = 0
            for i, point in enumerate(self.trajectory_points):
                if i > 0:
                    segment_distance = self._calculate_distance(
                        self.trajectory_points[i-1],
                        point
                    )
                    # 按比例增加距离
                    segment_distance += extra_distance * (segment_distance / total_distance)
                    segment_time = segment_distance / avg_speed
                    accumulated_time += segment_time * 1000  # 转为毫秒
                
                collect_time = base_time + int(accumulated_time)
                run_time = int(accumulated_time / 1000)
                
                # GPS精度设置
                if i == 0 or i == len(self.trajectory_points)-1:
                    accuracy = random.uniform(1.0, 3.0)
                else:
                    accuracy = 1.0 + min(1.0, avg_speed / 5.0) * 4.0
                
                # 处理不同类型的轨迹点格式
                if isinstance(point, (list, tuple)):
                    lng, lat = point
                elif isinstance(point, dict):
                    lng = point.get('lng')
                    lat = point.get('lat')
                else:
                    logger.warning(f"⚠️ 未知轨迹点格式: {type(point)}")
                    continue
                
                points.append(self._create_gps_point(
                    lng, lat, collect_time,
                    run_time=run_time, index=current_index,
                    accuracy=accuracy
                ))
                current_index += 1
            
            self.trajectory_index = current_index
            logger.info(f"✅ 生成 {len(points)} 个轨迹点 | 总距离: {self.distance:.2f}米（原始距离: {total_distance:.2f}米）")
            return points
        
        # 如果没有轨迹点，生成简单直线路径
        logger.info("ℹ️ 没有前端轨迹点，使用简单直线路径")
        num_points = 60
        
        if not self.start_location:
            self.start_location = (120.523568, 30.647431)
        
        base_lng, base_lat = self.start_location
        base_time = self.run_start_time
        points = []
        current_index = self.trajectory_index
        
        # 生成简单直线路径
        end_lng = base_lng + 0.001
        end_lat = base_lat + 0.001
        
        for i in range(num_points):
            ratio = i / (num_points - 1)
            lng = base_lng + (end_lng - base_lng) * ratio
            lat = base_lat + (end_lat - base_lat) * ratio
            
            # 添加轻微抖动
            if 0 < i < num_points - 1:
                lng += random.uniform(-0.00003, 0.00003)
                lat += random.uniform(-0.00003, 0.00003)
            
            collect_time = base_time + i * 3000
            run_time = (collect_time - base_time) // 1000
            
            points.append(self._create_gps_point(
                lng, lat, collect_time,
                run_time=run_time, index=current_index,
                accuracy=random.uniform(1.0, 5.0))
            )
            current_index += 1
        
        self.trajectory_index = current_index
        
        return points
    
    def _calculate_distance(self, point1, point2):
        """计算两点之间的地球表面距离（单位：米）"""
        import math
        
        # 处理 point1
        if isinstance(point1, (list, tuple)) and len(point1) == 2:
            lng1, lat1 = point1
        elif isinstance(point1, dict) and 'lng' in point1 and 'lat' in point1:
            lng1, lat1 = point1['lng'], point1['lat']
        else:
            raise ValueError(f"point1 格式无效: {type(point1)} {point1}")
        
        # 处理 point2
        if isinstance(point2, (list, tuple)) and len(point2) == 2:
            lng2, lat2 = point2
        elif isinstance(point2, dict) and 'lng' in point2 and 'lat' in point2:
            lng2, lat2 = point2['lng'], point2['lat']
        else:
            raise ValueError(f"point2 格式无效: {type(point2)} {point2}")
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lng1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lng2)
        
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        r = 6371000
        return c * r

    def _create_gps_point(self, lng, lat, collect_time, run_time, index, accuracy=None):
        if accuracy is None:
            accuracy = random.uniform(0.0, 2.0)
        
        return {
            "accuracy": accuracy,
            "collectTime": collect_time,
            "createTime": int(time.time() * 1000),
            "index": index,
            "lat": lat,
            "lng": lng,
            "offFenceDisM": -1,
            "runTime": run_time,
            "satellites": random.randint(9, 13),
            "state": 1
        }

    def validate_trajectory(self, points, min_distance=300):
        """验证轨迹，放宽距离限制"""
        logger = logging.getLogger('FreeRunClient')
        
        if len(points) < 10:
            logger.warning("⚠️ 轨迹点数量不足")
            return False
        
        time_diffs = []
        for i in range(len(points)-1):
            time_diffs.append(points[i+1]['collectTime'] - points[i]['collectTime'])
        
        max_diff = max(time_diffs) if time_diffs else 0
        if max_diff > 150000:
            logger.warning(f"⚠️ 轨迹点时间间隔过大（最大间隔: {max_diff}ms）")
            return False
        
        distance = 0
        for i in range(1, len(points)):
            segment_distance = self._calculate_distance(points[i-1], points[i])
            distance += segment_distance
        
        if distance < min_distance:
            logger.warning(f"⚠️ 轨迹总距离不足（{distance:.2f}米 < {min_distance}米）")
            return False
            
        logger.info(f"✅ 轨迹验证通过（点数: {len(points)}, 总距离: {distance:.2f}米）")
        return True
        
    def upload_pace_data(self):
        """上传配速数据"""
        try:
            pace_segments = self._generate_pace_segments()
            # 确保距离字段是整数
            for seg in pace_segments:
                seg["endDistance"] = int(seg["endDistance"])
                seg["startDistance"] = int(seg["startDistance"])
                seg["distance"] = int(seg["distance"])
            
            # 保存配速记录
            self.all_pace_records.extend(pace_segments)
            
            payload = {
                "modelName": self.model_name,
                "paceList": pace_segments,
                "appVersion": self.app_version,
                "buildVersion": self.build_version,
                "paceInterval": 50,
                "channel": self.channel,
                "appCode": self.app_code,
                "deviceId": self.device_id,
                "systemVersion": "12",
                "platform": "2",
                "runRecordCode": self.run_record_code,
                "timestamp": self.timestamp
            }
            
            # 打印索引信息
            indices = [s["index"] for s in pace_segments]
            print(f"📤 上传配速数据 | 索引: {indices}")
            
            # 发送请求并获取响应
            response = self._send_request('uploadPaceRecord', payload)
            
            # 处理响应并返回服务器确认的索引
            server_indices = []
            if response.get('code') == 0:
                data = response.get('data', {})
                server_indices = data.get('indexList', [])
                if server_indices:
                    print(f"✅ 配速数据上传成功 | 服务器确认索引: {server_indices}")
                else:
                    print("⚠️ 服务器未返回索引列表")
                    server_indices = [s["index"] for s in pace_segments]
            else:
                print(f"❌ 配速数据上传失败: {response.get('message')}")
            
            return server_indices
        
        except Exception as e:
            print(f"❌ 配速数据上传异常: {str(e)}")
            return []
        
    def upload_step_data(self):
        """上传步数数据"""
        step_records = self._generate_step_records()
        
        # 保存步数记录
        self.all_step_records.extend(step_records)
        
        payload = {
            "stepList": step_records,
            "stepInterval": 20,
            "runRecordCode": self.run_record_code,
            "deviceId": self.device_id,
            "timestamp": self.timestamp,
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "systemVersion": "12",
            "platform": "2"
        }
        
        # 发送请求
        response = self._send_request('uploadStepsRecord', payload)
        
        # 处理响应并返回索引
        indices = [r["index"] for r in step_records]
        server_indices = []
        
        if response and response.get("code") == 0:
            data = response.get("data", {})
            server_indices = data.get("indexList", [])
            if server_indices:
                print(f"✅ 步数数据上传成功 | 服务器确认索引: {server_indices}")
            else:
                print("⚠️ 服务器未返回索引列表")
                server_indices = indices
        else:
            print(f"❌ 步数数据上传失败: {response.get('message')}")
        
        return server_indices
    
    def upload_stride_data(self):
        """上传步幅数据"""
        stride_records = [
            {
                "distance": random.randint(190, 210),
                "index": self.stride_index_counter,
                "time": random.randint(65, 85),
                "stride": round(random.uniform(120.0, 160.0), 1),
                "stepCount": random.randint(120, 160)
            }
        ]
        
        payload = {
            "strideList": stride_records,
            "strideInterval": 200,
            "runRecordCode": self.run_record_code,
            "deviceId": self.device_id,
            "timestamp": self.timestamp,
            "modelName": self.model_name,
            "appVersion": self.app_version,
            "buildVersion": self.build_version,
            "channel": self.channel,
            "appCode": self.app_code,
            "systemVersion": "12",
            "platform": "2"
        }
        
        # 打印索引信息
        indices = [r["index"] for r in stride_records]
        print(f"📤 上传步幅数据 | 索引: {indices}")
        
        # 发送请求
        response = self._send_request('uploadStrideRecord', payload)
        
        # 处理响应并更新索引
        if response and response.get("code") == 0:
            data = response.get("data", {})
            server_indices = data.get("indexList", [])
            if server_indices:
                print(f"✅ 步幅数据上传成功 | 服务器确认索引: {server_indices}")
                if server_indices and server_indices[0] == self.stride_index_counter:
                    self.stride_index_counter += 1
                    print(f"🔄 更新步幅索引: {self.stride_index_counter}")
                else:
                    print(f"⚠️ 服务器索引不一致: 本地={self.stride_index_counter}, 服务器={server_indices}")
                    if server_indices:
                        self.stride_index_counter = max(server_indices) + 1
            else:
                print("⚠️ 服务器未返回索引列表")
                self.stride_index_counter += 1
        else:
            print(f"❌ 步幅数据上传失败: {response.get('message')}")
            self.stride_index_counter += 1
        
        return indices
    
    def _generate_pace_segments(self, num=3):
        """生成配速段数据"""
        segments = []
        for i in range(num):
            segment = {
                "endDistance": (i+1)*500,
                "startDistance": i*500,
                "distance": random.randint(45, 55),
                "endStepCount": (i+1)*400,
                "index": self.global_index_counter,
                "startTime": i*200,
                "endTime": (i+1)*200,
                "time": random.randint(15, 25),
                "stepCount": random.randint(30, 45),
                "stability": 0,
                "startStepCount": i*400
            }
            segments.append(segment)
            self.global_index_counter += 1
        return segments

    def _generate_step_records(self, num=3):
        """生成步数记录"""
        records = []
        for i in range(num):
            records.append({
                "endStep": (i+1)*500,
                "index": self.global_index_counter,
                "startTime": i*20,
                "step": random.randint(35, 50),
                "endTime": (i+1)*20,
                "startStep": i*500,
                "time": 20,
                "stability": 0
            })
            self.global_index_counter += 1
        return records

    def get_realistic_pois(self):
        """获取结束跑步前的最后几个轨迹点"""
        logger = logging.getLogger('FreeRunClient')
        
        # 使用前端传递的轨迹点
        if self.trajectory_points and len(self.trajectory_points) >= 3:
            last_three = self.trajectory_points[-3:]
            current_time = int(time.time() * 1000)
            pois = []
            
            for i, point in enumerate(last_three):
                # 处理不同类型的轨迹点格式
                if isinstance(point, (list, tuple)):
                    lng, lat = point
                elif isinstance(point, dict):
                    lng = point.get('lng')
                    lat = point.get('lat')
                else:
                    logger.warning(f"⚠️ 未知轨迹点格式: {type(point)}")
                    continue
                    
                pois.append({
                    "lng": lng,
                    "lat": lat,
                    "stability": 0
                })
            return pois
        
        # 如果没有轨迹点，使用默认点
        current_time = int(time.time() * 1000)
        return [
            {
                "lng": self.start_location[0],
                "lat": self.start_location[1],
                "stability": 0
            },
            {
                "lng": self.start_location[0] + 0.0001,
                "lat": self.start_location[1] + 0.0001,
                "stability": 0
            },
            {
                "lng": self.start_location[0] + 0.0002,
                "lat": self.start_location[1] + 0.0002,
                "stability": 0
            }
        ]
    
    def generate_sign(self, payload):
        return "generated_signature"
    
    def handle_1006_error(self, response=None):
        print("\n🚀 执行1006错误恢复流程...")
        self.retry_delay = 30
        print(f"⏱️ 延长重试等待时间至 {self.retry_delay}秒")
        time.sleep(self.retry_delay)
        self.timestamp = str(int(time.time() * 1000))
        print(f"🔄 更新时间戳: {self.timestamp}")
        
        # 尝试重新启动
        try:
            if self.start_free_run():
                self.upload_run_data()
                self.simulate_running()
                self.finish_free_run()
                print("✅✅✅ 1006错误恢复成功 ✅✅✅")
                return True
        except Exception as e:
            print(f"❌ 1006错误恢复失败: {str(e)}")
        
        print("❌❌❌ 1006错误恢复失败 ❌❌❌")
        return False

    def _send_request(self, endpoint, payload, special_api=False, retries=3, api_module=None, api_version=None):
        if special_api:
            url = f"http://api.huachenjie.com/run-front/{endpoint}"
        else:
            url = f"{self.base_url}/{endpoint}"
        
        headers = {
            "User-Agent": "ShanDong/7.9.4 (Xiaomi;Android 12)",
            "Content-Type": "application/json;charset=UTF-8",
            "Host": "api.huachenjie.com",
            "Authorization": f"Bearer {self.auth_token}",
            "satoken": self.satoken,
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        
        if special_api:
            if not api_module:
                if endpoint.startswith("run/"):
                    api_module = "run"
                else:
                    api_module = "run"
            if not api_version:
                parts = endpoint.split('/')
                api_version = parts[-1] if parts else endpoint
            special_headers = {
                "app": "run-front",
                "e": "0",
                "v": api_version,
                "pv": "2",
                "api": api_module,
                "k": ""
            }
            headers.update(special_headers)
            print(f"🔧 特殊接口头部: api={api_module}, v={api_version}")
        
        try:
            json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            signature = self.makesign(json_str)
            headers["sign"] = signature
            print(f"🔏 生成签名: {signature}")
        except Exception as e:
            print(f"❌ 签名生成失败: {str(e)}")
            raise
        
        print(f"🌐 请求URL: {url}")

        if self.proxy:
            print(f"🔌 使用代理: {self.proxy}")
        
        for attempt in range(retries):
            try:
                print(f"🔄 尝试 {attempt+1}/{retries}")
                response = self.session.post(
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=15,
                    verify=False
                )
                print(f"📡 状态码: {response.status_code}")
                
                # 尝试解析JSON响应
                try:
                    json_response = response.json()
                    print(f"📡 响应内容: {json.dumps(json_response, ensure_ascii=False)[:500]}")
                    
                    # 检查响应中的错误代码
                    if 'code' in json_response:
                        code = json_response['code']
                        self.last_error_code = code
                        
                        # 检测授权失效错误代码
                        if code in self.auth_error_codes:
                            self.auth_expired = True
                            print(f"⚠️ 检测到授权失效，错误码: {code}, 消息: {json_response.get('message')}")
                    
                    return json_response
                except json.JSONDecodeError:
                    print(f"⚠️ 响应不是JSON格式，返回原始文本")
                    print(f"📡 原始响应: {response.text[:500]}")
                    return {"raw_response": response.text}
            except requests.exceptions.RequestException as e:
                print(f"❌ 请求失败: {str(e)}")
                if attempt == retries - 1:
                    raise
                delay = min(10, 2 ** attempt)
                print(f"⏱ 等待 {delay} 秒后重试...")
                time.sleep(delay)
        print(f"❌❌ 所有 {retries} 次尝试均失败")
        return None
    
    @staticmethod
    def makesign(body):
        sha = hashlib.sha256()
        sha.update(body.encode('utf-8'))
        hex_hash = sha.hexdigest()
        
        swapped_hash = hex_hash[-8:] + hex_hash[8:-8] + hex_hash[:8]
        
        original_key = "RHXL092CDOYTQJVP"
        key_bytes = original_key.encode("utf-8")
        padded_key = key_bytes.ljust(32, b"\x00")
        
        iv = b'01234ABCDEF56789'
        
        raw_data = swapped_hash.encode("utf-8")
        raw_data_padded = pad(raw_data, AES.block_size)
        
        cipher = AES.new(padded_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(raw_data_padded)
        
        sign = base64.b64encode(encrypted).decode("utf-8")
        return sign
    
class StartRunError(Exception):
    def __init__(self, code, message, response=None):
        self.code = code
        self.message = message
        self.response = response
        super().__init__(f"[{code}] {message}")

def main_wrapper():
    # 初始化变量
    callback_url = "http://yangrun.xyz/update_order_status.php"  # 替换为您的实际回调URL
    orderid = None
    status = 3  # 默认状态为失败
    remark = ""
    log_path = ""
    
    try:
        # 设置日志
        log_path = setup_logging()
        logger = setup_logger(log_path)
        
        logger.info("===== 自由跑脚本启动 =====")
        # 记录接收到的所有参数
        logger.info(f"命令行参数: {sys.argv}")
        # 检查参数
        if len(sys.argv) < 3:
            error_msg = "错误：参数不足，需要JSON参数和订单ID,实际收到 {len(sys.argv)-1} 个参数"
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
            logger.info("创建FreeRunClient实例...")
            client = FreeRunClient(
                device_id=params['device_id'],
                auth_token=params['auth_token'],
                satoken=params['satoken'],
                distance=params['distance'],
                total_step=params['total_step'],
                duration=params['duration'],
                face_image_path=params.get('face_image_path'),
                proxy=params.get('proxy', "http://121.40.95.86"),
                trajectory_points=params.get('trajectory_points')
            )
            logger.info("客户端创建成功")
        except Exception as e:
            error_msg = f"创建客户端失败: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            remark = error_msg
            status = 3
            sys.exit(1)
        
        # 执行自由跑
        try:
            logger.info("开始执行自由跑流程...")
            success = client.run_free_run()
            
            if success:
                logger.info("自由跑执行成功")
                print("🎉 完成！")
                status = 2  # 成功
                remark = "执行成功"
            else:
                logger.error("自由跑执行失败")
                print("❌ 失败")
                
                # 根据授权状态设置备注
                if client.auth_expired:
                    remark = f"授权失效 (错误码: {client.last_error_code})"
                else:
                    remark = "脚本执行失败，未返回成功状态"
                
                status = 3  # 失败
        except Exception as e:
            error_msg = f"自由跑执行异常: {str(e)}"
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
                    'remark': remark,
                    'error_code': client.last_error_code if 'client' in locals() else 0
                }
                
                logger.info(f"发送状态回调: {callback_params}")
                
                # 发送回调请求
                response = requests.get(callback_url, params=callback_params, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"回调成功: {response.text}")
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