import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
import requests
import json
import time
import random
from typing import Dict, List, Any, Optional
import os
import tempfile
import sys
import traceback
import math
import uuid
import hmac
import xml.etree.ElementTree as ET
import ssl
import http.client
from datetime import datetime, timezone, timedelta
import urllib3
from urllib.parse import urlparse, quote
from requests.adapters import HTTPAdapter

class AuthExpiredException(Exception):
    """授权过期异常"""
    def __init__(self, error_code, message):
        self.error_code = error_code
        self.message = message
        super().__init__(f"授权过期 (错误码: {error_code}): {message}")

class RealisticPathGenerator:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "http://restapi.amap.com/v3/direction/walking"

    def generate_path(self, origin, destination, total_duration):
        raw_points = self._get_walking_path(origin, destination)
        if not raw_points:
            return self._generate_natural_path(origin, destination, total_duration)
        return self._add_timing(raw_points, total_duration)
    
    def _get_walking_path(self, origin, destination):
        params = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "key": self.api_key,
            "output": "json"
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            if data["status"] == "1" and data["route"]["paths"]:
                path = data["route"]["paths"][0]
                steps = path["steps"]
                
                all_points = []
                for step in steps:
                    polyline = step["polyline"]
                    points = polyline.split(";")
                    for point in points:
                        lng, lat = point.split(",")
                        all_points.append((float(lng), float(lat)))
                return all_points
        except Exception:
            pass
        return None
    
    def _generate_natural_path(self, origin, destination, total_duration, num_points=50):
        """生成更自然的跑步路径（使用贝塞尔曲线和速度变化）"""
        lng1, lat1 = origin
        lng2, lat2 = destination
        
        # 计算路径方向向量
        dx = lng2 - lng1
        dy = lat2 - lat1
        distance = math.sqrt(dx**2 + dy**2)
        
        # 生成控制点（模拟自然转弯）
        control_points = []
        
        # 随机决定转弯次数（1-3次）
        num_turns = random.randint(1, 3)
        for i in range(num_turns):
            # 随机转弯位置（在路径的25%-75%之间）
            turn_pos = 0.25 + random.random() * 0.5
            
            # 随机转弯方向（左转或右转）
            turn_direction = 1 if random.random() > 0.5 else -1
            
            # 转弯强度（基于总距离）
            turn_strength = random.uniform(0.2, 0.5) * distance
            
            # 计算控制点位置
            control_lng = lng1 + dx * turn_pos + turn_direction * dy * turn_strength
            control_lat = lat1 + dy * turn_pos - turn_direction * dx * turn_strength
            control_points.append((control_lng, control_lat))
        
        # 生成贝塞尔曲线路径点
        points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            
            # 三次贝塞尔曲线计算
            if num_turns == 1:
                # 单控制点曲线
                lng = (1-t)**3 * lng1 + 3*(1-t)**2*t*control_points[0][0] + 3*(1-t)*t**2*lng2 + t**3*lng2
                lat = (1-t)**3 * lat1 + 3*(1-t)**2*t*control_points[0][1] + 3*(1-t)*t**2*lat2 + t**3*lat2
            elif num_turns >= 2:
                # 双控制点曲线
                lng = (1-t)**3 * lng1 + 3*(1-t)**2*t*control_points[0][0] + 3*(1-t)*t**2*control_points[1][0] + t**3*lng2
                lat = (1-t)**3 * lat1 + 3*(1-t)**2*t*control_points[0][1] + 3*(1-t)*t**2*control_points[1][1] + t**3*lat2
            else:
                # 无控制点（直线）
                lng = lng1 + dx * t
                lat = lat1 + dy * t
            
            # 添加微小随机扰动（模拟GPS漂移）
            jitter_x = random.gauss(0, 0.00005)
            jitter_y = random.gauss(0, 0.00005)
            
            # 添加路径"记忆"效应 - 保持部分前一点的方向
            if i > 0:
                prev_lng, prev_lat = points[i-1]
                direction_strength = 0.7
                lng = direction_strength * lng + (1-direction_strength) * (prev_lng + (lng - prev_lng))
                lat = direction_strength * lat + (1-direction_strength) * (prev_lat + (lat - prev_lat))
            
            points.append((lng + jitter_x, lat + jitter_y))
        
        return self._add_timing(points, total_duration, curve_points=control_points)
    
    def _add_timing(self, points, total_duration, curve_points=None):
        """添加时间戳和速度变化"""
        total_distance = 0
        segment_distances = []
        
        # 计算每段距离
        for i in range(1, len(points)):
            dist = self._calculate_distance(points[i-1], points[i])
            total_distance += dist
            segment_distances.append(dist)
        
        timed_points = []
        current_time = int(time.time())
        accumulated_distance = 0
        
        # 跑步速度变化曲线（起步慢，中途快，结束慢）
        base_speed = 2.5
        speed_profile = []
        
        # 生成速度曲线（0-1标准化距离）
        for i in range(len(points)):
            t = i / (len(points)-1)
            speed_variation = 0.5 * math.sin(math.pi * t - math.pi/2) + 0.8
            speed_profile.append(base_speed * speed_variation)
        
        for i in range(len(points)):
            if i > 0:
                segment_distance = segment_distances[i-1]
                accumulated_distance += segment_distance
                
                # 当前速度（基于位置在速度曲线中的位置）
                current_speed = speed_profile[i]
                
                # 添加随机速度波动（±15%）
                speed_variation = random.uniform(0.85, 1.15)
                current_speed *= speed_variation
                
                segment_time = segment_distance / current_speed
                current_time += segment_time
            
            # GPS精度随速度变化（速度越快精度越低）
            if i == 0 or i == len(points)-1:
                accuracy = random.uniform(1.0, 3.0)
            else:
                speed_factor = min(1.0, current_speed / 5.0)
                accuracy = 1.0 + speed_factor * 4.0
            
            timed_points.append({
                "lng": points[i][0],
                "lat": points[i][1],
                "timestamp": int(current_time),
                "accuracy": accuracy,
                "speed": current_speed if i > 0 else 0
            })
        
        return timed_points

    def _calculate_distance(self, point1, point2):
        from math import radians, sin, cos, sqrt, atan2
        
        lat1, lon1 = radians(point1[1]), radians(point1[0])
        lat2, lon2 = radians(point2[1]), radians(point2[0])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        R = 6371000
        return R * c

# 配置信息
modelName = "Xiaomi|2206122SC"
appVersion = "8.1.8"
buildVersion = "25110817"
deviceId = "a3473319f90c256e"
systemVersion = "12"
Authorization = "eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjI0MTAxMDA4MTYwMDkwMDQ0LCJleHAiOjE3Njc2Mjg4MDAsInBob25lIjoiMTkxMjAyNzMxMzQiLCJpYXQiOjE3NjI1MTkwMTN9.3ubZ9sGik3KJavGDyLKs2-1pb0j3SH5_EagU8igvH9w"
satoken = "7da7f7f1-c50a-43ba-8355-f90a9113b814"
UA = "ShanDong/8.1.8 (Xiaomi;Android 12)"
appCode = "SD001"
channel = "other"
platform = "2"

# API端点
PLAN_SELECT_LIST = "/run-front/run/plan/selectList"
QUERY_SCHOOL_FENCES = "/run-front/school/querySchoolFences"
START_SUNRUN = "/run-front/run/startSunRun"
UPLOAD_RUN_RECORD = "/run-front/run/uploadRunRecord"
UPLOAD_PACE_RECORD = "/run-front/run/uploadPaceRecord"
UPLOAD_STRIDE_RECORD = "/run-front/run/uploadStrideRecord"
UPLOAD_STEPS_RECORD = "/run-front/run/uploadStepsRecord"
UPLOAD_PASS_POINT = "/run-front/run/uploadPassPoint"
FINISH_SUN_RUN = "/run-front/run/finishSunRun"

BASE_URL = "http://api.huachenjie.com"

# 全局变量
path_generator = None
proxy = None
face_image_path = None
api_key = "6d05ae2d40c8812bbdd40194e95f256e"
selected_run_plan_code = None
selected_fence_code = None
selected_semester_code = None
# 新增：活动跑相关全局变量
activity_run_code = None  # 存储活动代码
def makesign(body):
    """生成签名"""
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

def calculate_run_img_record(run_record_code: str, timestamp: int) -> str:
    """计算runImgRecord"""
    run_img_record_key = "2V8BQ8MYXWU10Y9Z" 
    
    data = f"{run_record_code}{buildVersion}{appVersion}{run_img_record_key}{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()

def send_post_request(url, body, extra_headers=None):
    """发送POST请求"""
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
        
        # 检查响应是否包含授权失效错误
        if response and response.status_code == 200:
            try:
                data = response.json()
                error_code = data.get("code")
                if error_code in [1503, 1516]:
                    error_msg = data.get("message", "授权状态已失效")
                    raise AuthExpiredException(error_code, error_msg)
            except (ValueError, AttributeError):
                pass
        
        return response
    except requests.exceptions.RequestException:
        return None

def get_activity_list():
    """获取活动跑列表 - 从活动跑规则.py复制过来"""
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
def get_ongoing_activity():
    """获取进行中的活动跑"""
    activity_data = get_activity_list()
    if not activity_data:
        return None
    
    activity_list = activity_data.get("activityList", [])
    if not activity_list:
        return None
    
    # 查找状态为1（进行中）的活动
    for activity in activity_list:
        if activity.get('activityStatus') == 1:  # 1表示进行中
            return activity
    
    return None

def get_plans():
    """获取跑步计划列表"""
    global selected_semester_code, selected_run_plan_code
    
    url = BASE_URL + PLAN_SELECT_LIST
    timestamp = str(int(time.time() * 1000))
    
    # 如果指定了学期代码，只使用该代码
    if selected_semester_code:
        semester_codes = [selected_semester_code]
    else:
        # 否则遍历所有可能的学期代码
        semester_codes = [""] + [str(i) for i in range(1, 21)]
    
    # 遍历学期代码
    for semester_code in semester_codes:
        body = {
            "modelName": modelName,
            "appVersion": appVersion,
            "buildVersion": buildVersion,
            "semesterCode": semester_code,
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
            "v": "plan",
            "pv": "2",
            "api": "run",
            "k": ""
        }
        
        response = send_post_request(url, body, extra_headers)
        if response and response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                plans_data = data.get("data", {})
                plan_list = plans_data.get("list", [])
                
                # 如果指定了计划代码，查找匹配的计划
                if selected_run_plan_code:
                    matched_plan = None
                    for plan in plan_list:
                        if plan.get('runPlanCode') == selected_run_plan_code:
                            matched_plan = plan
                            break
                    
                    if matched_plan:
                        plans_data["list"] = [matched_plan]
                        return plans_data
                else:
                    # 筛选激活的计划
                    active_plans = [plan for plan in plan_list if plan.get('planStatus') == 1]
                    
                    if active_plans:
                        plans_data["list"] = active_plans
                        return plans_data
    
    return None

def get_school_fences(school_code):
    """获取学校围栏信息"""
    global selected_fence_code
    
    url = BASE_URL + QUERY_SCHOOL_FENCES
    timestamp = str(int(time.time() * 1000))
    
    body = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "channel": channel,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "schoolCode": school_code,
        "timestamp": timestamp
    }
    
    extra_headers = {
        "app": "run-front",
        "e": "0",
        "v": "querySchoolFences",
        "pv": "2",
        "api": "school",
        "k": ""
    }
    
    response = send_post_request(url, body, extra_headers)
    if response and response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            fences_data = data.get("data", [])
            
            # 如果指定了围栏代码，查找匹配的围栏
            if selected_fence_code:
                matched_fence = None
                for fence in fences_data:
                    if fence.get('fenceCode') == selected_fence_code:
                        matched_fence = fence
                        break
                
                if matched_fence:
                    return [matched_fence]
                else:
                    return fences_data
            else:
                return fences_data
    return None

def query_unfinish_run():
    """查询是否有未完成的跑步记录"""
    url = BASE_URL + "/run-front/run/queryUnFinishRun"
    timestamp = str(int(time.time() * 1000))
    
    body = {
        "modelName": modelName,
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
        "v": "queryUnFinishRun",
        "pv": "2",
        "api": "run",
        "k": ""
    }
    
    response = send_post_request(url, body, extra_headers)
    if response and response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            # 检查是否有未完成的跑步记录
            if data.get("data") and data["data"].get("runRecordCode"):
                return data["data"]["runRecordCode"]
    return None

def force_finish_run(run_record_code, fence_center_lat, fence_center_lng):
    """强制结束未完成的跑步记录，使用围栏中心坐标生成打卡点"""
    url = BASE_URL + FINISH_SUN_RUN
    timestamp = str(int(time.time() * 1000))
    
    run_img_record = calculate_run_img_record(run_record_code, int(timestamp))
    
    # 生成基于围栏中心的打卡点
    target_points = []
    num_points = 3
    for i in range(num_points):
        # 在围栏中心周围生成随机偏移的点
        offset_lng = random.uniform(-0.001, 0.001)
        offset_lat = random.uniform(-0.001, 0.001)
        
        target_points.append({
            "code": int(f"23{random.randint(1000000000, 9999999999)}"),
            "lng": fence_center_lng + offset_lng,
            "passStatus": False,
            "lat": fence_center_lat + offset_lat,
            "clockTime": 0
        })
    
    # 构建强制结束的请求体
    body = {
        "pauseTimes": 1,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "stepInterval": 20,
        "distance": "0",
        "totalStep": "0",
        "channel": channel,
        "runImgRecord": "fec977ef64699b59179935e2f0797f4f",
        "targetPoints": target_points,
        "alignType": 3,
        "stepList": [{
            "endStep": 0,
            "index": 2147483647,
            "startTime": 0,
            "step": 0,
            "endTime": 7,
            "startStep": 0,
            "time": 7,
            "stability": 0
        }],
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "invalidReasons": [
            {
                "invalidDetail": "公里数不足2.00公里基本要求",
                "invalidType": 2,
                "stability": 0
            },
            {
                "invalidDetail": f"只完成0个打卡点，还有{num_points}个未完成",
                "invalidType": 1,
                "stability": 0
            }
        ],
        "platform": platform,
        "runRecordCode": run_record_code,
        "duration": "7",
        "modelName": modelName,
        "paceList": [{
            "endDistance": 0,
            "startDistance": 0,
            "distance": 0,
            "endStepCount": 0,
            "index": 82,
            "startTime": 0,
            "endTime": 6,
            "time": 6,
            "stepCount": 0,
            "stability": 0,
            "startStepCount": 0
        }],
        "paceInterval": 50,
        "pauseCount": 1,
        "pois": [{
            "satellites": 5,
            "collectTime": int(time.time() * 1000) - 10000,
            "offFenceDisM": -1,
            "lng": fence_center_lng,
            "createTime": int(time.time() * 1000) - 9700,
            "accuracy": 1.0,
            "index": 433,
            "runTime": 0,
            "state": 1,
            "lat": fence_center_lat
        }],
        "status": 0,
        "timestamp": timestamp
    }
    
    response = send_post_request(url, body)
    if response and response.status_code == 200:
        data = response.json()
        return data.get("code") == 0
    return False

def start_activity_run(run_plan_code, activity_code, fence_code, school_code, lat, lng):
    """开始活动跑 - 同时传入跑步计划代码和活动代码"""
    url = BASE_URL + START_SUNRUN
    timestamp = str(int(time.time() * 1000))
    
    body = {
        "useCreditSword": "false",
        "runPlanCode": run_plan_code,  # 保持原有的跑步计划代码
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "lng": lng,
        "channel": channel,
        "targetDistance": "0",
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "modelName": modelName,
        "fenceCode": fence_code,
        "lat": lat,
        "schoolCode": school_code,
        "timestamp": timestamp
    }
    
    # 如果有活动代码，添加到请求体中
    if activity_code:
        body["activityCode"] = activity_code
    
    extra_headers = {
        "app": "run-front",
        "e": "0",
        "v": "startSunRun",
        "pv": "2",
        "api": "run",
        "k": ""
    }
    
    response = send_post_request(url, body, extra_headers)
    if response and response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            return data.get("data", {})
        else:
            error_msg = data.get("message", "开始跑步失败")
            if data.get("data") and isinstance(data.get("data"), dict):
                detail_msg = data.get("data").get("message")
                if detail_msg:
                    error_msg = f"{error_msg}: {detail_msg}"
            return {"error": error_msg, "code": data.get("code")}
    return {"error": "开始跑步请求失败", "code": -1}

def upload_run_record_batch(run_record_code, pois_batch, timestamp, batch_number):
    """分批次上传跑步记录"""
    url = BASE_URL + UPLOAD_RUN_RECORD
    body = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "channel": channel,
        "appCode": appCode,
        "pois": pois_batch,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "runRecordCode": run_record_code,
        "timestamp": timestamp
    }
    
    response = send_post_request(url, body)
    if response and response.status_code == 200:
        data = response.json()
        success = data.get("code") == 0
        return success
    else:
        return False

def upload_all_pois_in_batches(run_record_code, pois, batch_size=50):
    """分批次上传所有轨迹点"""
    total_pois = len(pois)
    batches = []
    
    # 将轨迹点分成多个批次
    for i in range(0, total_pois, batch_size):
        batch = pois[i:i + batch_size]
        batches.append(batch)
    
    # 依次上传每个批次
    success_count = 0
    for i, batch in enumerate(batches):
        batch_timestamp = str(int(time.time() * 1000))
        
        # 上传当前批次
        if upload_run_record_batch(run_record_code, batch, batch_timestamp, i + 1):
            success_count += 1
        
        # 批次间短暂延迟，模拟真实上传节奏
        if i < len(batches) - 1:
            time.sleep(0.5)
    
    return success_count == len(batches)

def upload_pass_point(run_record_code, target_points, timestamp):
    """上传通过点 - 所有点都标记为通过"""
    url = BASE_URL + UPLOAD_PASS_POINT
    
    # 确保所有点都标记为通过
    for point in target_points:
        point["passStatus"] = True
        # 如果clockTime为0，设置为当前时间
        if point.get("clockTime", 0) == 0:
            point["clockTime"] = int(time.time() * 1000)
    
    body = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "channel": channel,
        "targetPoints": target_points,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "runRecordCode": run_record_code,
        "timestamp": timestamp
    }
    
    response = send_post_request(url, body)
    if response and response.status_code == 200:
        data = response.json()
        return data.get("code") == 0
    return False

def upload_pace_record(run_record_code, pace_list, timestamp):
    """上传配速记录"""
    url = BASE_URL + UPLOAD_PACE_RECORD
    
    body = {
        "modelName": modelName,
        "paceList": pace_list,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "paceInterval": 50,
        "channel": channel,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "runRecordCode": run_record_code,
        "timestamp": timestamp
    }
    
    response = send_post_request(url, body)
    if response and response.status_code == 200:
        data = response.json()
        return data.get("code") == 0
    return False

def upload_steps_record(run_record_code, step_list, timestamp):
    """上传步数记录"""
    url = BASE_URL + UPLOAD_STEPS_RECORD
    
    body = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "stepInterval": 20,
        "channel": channel,
        "stepList": step_list,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "runRecordCode": run_record_code,
        "timestamp": timestamp
    }
    
    response = send_post_request(url, body)
    if response and response.status_code == 200:
        data = response.json()
        return data.get("code") == 0
    return False

def upload_stride_record(run_record_code, stride_list, timestamp):
    """上传步幅记录"""
    url = BASE_URL + UPLOAD_STRIDE_RECORD
    
    body = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "channel": channel,
        "strideList": stride_list,
        "appCode": appCode,
        "strideInterval": 200,
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "runRecordCode": run_record_code,
        "timestamp": timestamp
    }
    
    response = send_post_request(url, body)
    if response and response.status_code == 200:
        data = response.json()
        return data.get("code") == 0
    return False

def finish_sunrun(run_record_code, distance, total_step, duration, pois, pace_list, step_list, target_points, timestamp, face_file_path=None, face_img_url=None):
    """完成阳光跑 - 更新人脸识别参数结构"""
    url = BASE_URL + FINISH_SUN_RUN
    
    # 计算动态的runImgRecord
    run_img_record = calculate_run_img_record(run_record_code, int(timestamp))
    
    # 构建基础请求体
    body = {
        "pauseTimes": 0,
        "sportType": 1,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "stepInterval": 20,
        "distance": float(distance),
        "totalStep": int(total_step),
        "channel": channel,
        "runImgRecord": run_img_record,
        "targetPoints": target_points,
        "alignType": 3,
        "stepList": step_list,
        "appCode": appCode,
        "deviceId": deviceId,
        "systemVersion": 12,
        "platform": platform,
        "runRecordCode": run_record_code,
        "duration": int(duration),
        "modelName": modelName,
        "paceList": pace_list,
        "paceInterval": 50,
        "pauseCount": 0,
        "pois": pois[-4:],  # 只上传最后4个点
        "status": 1,
        "timestamp": timestamp
    }
    
    # 如果提供了人脸图片URL，构建新的faceCheckRecordList结构
    if face_img_url and face_file_path:
        # 生成人脸识别相关信息
        face_request_id = str(uuid.uuid4()).upper()
        check_distance = random.randint(500, 600)
        random_distance = random.randint(500, 600)
        
        # 使用最后一个轨迹点的坐标作为检查点坐标
        check_lng = pois[-1]["lng"] if pois else 120.344153
        check_lat = pois[-1]["lat"] if pois else 30.322339
        
        # 构建新的faceCheckRecordList结构
        face_check_record = {
            "checkDistance": check_distance,
            "randomDistance": random_distance,
            "runFaceImg": face_img_url,
            "checkLng": check_lng,
            "confidence": round(random.uniform(85.0, 95.0), 5),
            "checkIndex": 1,
            "runFaceUpload": True,
            "popTime": int(time.time() * 1000) - random.randint(5000, 10000),
            "checkLat": check_lat,
            "hasChecked": True,
            "faceRequestId": face_request_id,
            "finishFaceCheck": True,
            "extendParam": json.dumps({
                "filePath": face_file_path,
                "fileUrl": face_img_url,
                "progress": "uploading->success->compare->success"
            }, ensure_ascii=False),
            "stability": 0
        }
        
        body["faceCheckRecordList"] = [face_check_record]
    
    response = send_post_request(url, body)
    result = {"success": False, "message": "请求失败", "data": {}}
    
    if response:
        try:
            response_data = response.json()
            
            if response.status_code == 200:
                result["data"] = response_data.get("data", {})
                
                if response_data.get("code") == 0:
                    # 检查跑步状态
                    if result["data"].get("status") == 1:
                        result["success"] = True
                        result["message"] = "跑步完成成功！"
                    else:
                        # 跑步失败，提取错误信息
                        alert_tip = result["data"].get("alertTip", {})
                        error_content = alert_tip.get("content", "跑步失败，未知原因")
                        result["message"] = f"跑步失败: {error_content}"
                else:
                    error_msg = response_data.get("message", "未知错误")
                    result["message"] = f"完成跑步失败: {error_msg}"
            else:
                result["message"] = f"HTTP错误: {response.status_code}"
        except Exception as e:
            result["message"] = f"解析响应失败: {str(e)}"
    else:
        result["message"] = "完成跑步请求无响应"
    
    return result
    
def generate_realistic_pois(base_lat, base_lng, start_time, interval=3, trajectory_points=None, target_points=None):
    """生成真实的轨迹点，确保精确经过所有打卡点，不考虑点数限制"""
    global path_generator
    
    if not path_generator:
        path_generator = RealisticPathGenerator(api_key)
    
    # 如果有前端传入的轨迹点，直接使用这些点
    if trajectory_points:
        try:
            # 解析轨迹点字符串
            points = json.loads(trajectory_points)
            
            pois = []
            current_time = start_time
            
            for i, point in enumerate(points):
                poi = {
                    "accuracy": random.uniform(1.0, 3.0),
                    "collectTime": current_time,
                    "createTime": current_time + 867,
                    "index": i + 1,
                    "lat": point[1],
                    "lng": point[0],
                    "offFenceDisM": -1,
                    "runTime": i * interval,
                    "satellites": random.randint(5, 13),
                    "state": 1
                }
                pois.append(poi)
                current_time += interval * 1000
            
            return pois
        except Exception:
            pass
    
    # 如果有打卡点，确保轨迹精确经过每个打卡点
    if target_points and len(target_points) >= 2:
        all_points = []
        
        # 第一步：确保每个打卡点都在路径中
        for i, target_point in enumerate(target_points):
            # 将打卡点本身添加到路径中
            all_points.append({
                "lng": target_point['lng'],
                "lat": target_point['lat'],
                "accuracy": 1.0,
                "is_target_point": True
            })
            
            # 如果不是最后一个打卡点，生成到下一个打卡点的路径
            if i < len(target_points) - 1:
                start_point = (target_point['lng'], target_point['lat'])
                end_point = (target_points[i + 1]['lng'], target_points[i + 1]['lat'])
                
                # 计算两点间距离
                segment_distance = path_generator._calculate_distance(start_point, end_point)
                
                # 根据距离动态计算需要的点数（每2-3米一个点，确保路径平滑）
                segment_points = max(15, int(segment_distance / 3))
                
                # 使用高德地图API获取真实路径
                segment_duration = int(segment_distance / 2.5)
                segment_path = path_generator.generate_path(start_point, end_point, segment_duration)
                
                if segment_path:
                    # 将路径点添加到总路径中（去掉起点，避免重复）
                    for point_data in segment_path[1:]:
                        all_points.append({
                            "lng": point_data["lng"],
                            "lat": point_data["lat"],
                            "accuracy": point_data.get("accuracy", random.uniform(1.0, 3.0)),
                            "is_target_point": False
                        })
                else:
                    # 高德API失败，生成更密集的直线路径
                    for j in range(1, segment_points):
                        progress = j / segment_points
                        lng = start_point[0] + (end_point[0] - start_point[0]) * progress
                        lat = start_point[1] + (end_point[1] - start_point[1]) * progress
                        
                        # 添加微小随机扰动，使直线路径更自然
                        jitter_lng = random.gauss(0, 0.000015)
                        jitter_lat = random.gauss(0, 0.000015)
                        
                        all_points.append({
                            "lng": lng + jitter_lng,
                            "lat": lat + jitter_lat,
                            "accuracy": random.uniform(2.0, 4.0),
                            "is_target_point": False
                        })
        
        # 第二步：在现有路径点之间插入额外点，使路径更平滑
        smoothed_points = []
        
        for i in range(len(all_points)):
            # 添加当前点
            smoothed_points.append(all_points[i])
            
            # 如果不是最后一个点，且当前点和下一个点都不是打卡点，考虑插入中间点
            if i < len(all_points) - 1:
                current_point = all_points[i]
                next_point = all_points[i + 1]
                
                # 计算两点距离
                dist = path_generator._calculate_distance(
                    (current_point["lng"], current_point["lat"]),
                    (next_point["lng"], next_point["lat"])
                )
                
                # 如果距离较大（大于8米），插入中间点
                if dist > 8 and not current_point.get("is_target_point") and not next_point.get("is_target_point"):
                    # 根据距离决定插入点数（每4-6米插入一个点）
                    num_insert = max(1, int(dist / 5))
                    
                    for j in range(1, num_insert + 1):
                        progress = j / (num_insert + 1)
                        lng = current_point["lng"] + (next_point["lng"] - current_point["lng"]) * progress
                        lat = current_point["lat"] + (next_point["lat"] - current_point["lat"]) * progress
                        
                        # 添加微小扰动
                        jitter_lng = random.gauss(0, 0.000008)
                        jitter_lat = random.gauss(0, 0.000008)
                        
                        smoothed_points.append({
                            "lng": lng + jitter_lng,
                            "lat": lat + jitter_lat,
                            "accuracy": random.uniform(2.0, 3.5),
                            "is_target_point": False
                        })
        
        all_points = smoothed_points
        
        # 第三步：添加时间信息，生成最终的POIs
        pois = []
        current_time = start_time
        
        for i, point in enumerate(all_points):
            poi = {
                "accuracy": point.get("accuracy", random.uniform(1.0, 3.0)),
                "collectTime": current_time,
                "createTime": current_time + 867,
                "index": i + 1,
                "lat": point["lat"],
                "lng": point["lng"],
                "offFenceDisM": -1,
                "runTime": i * interval,
                "satellites": random.randint(5, 13),
                "state": 1
            }
            pois.append(poi)
            current_time += interval * 1000
        
        return pois
    
    # 默认情况：没有打卡点，使用操场圆形路径
    # 生成圆形路径（模拟操场）
    center_lng, center_lat = float(base_lng), float(base_lat)
    radius = 0.001
    
    points = []
    num_circles = 3
    
    # 计算每圈点数（更密集）
    points_per_circle = 100
    
    for circle in range(num_circles):
        for i in range(points_per_circle):
            angle = 2 * math.pi * i / points_per_circle
            # 添加微小随机偏移，使路径更自然
            jitter_lng = random.gauss(0, 0.000015)
            jitter_lat = random.gauss(0, 0.000015)
            
            lng = center_lng + radius * math.cos(angle) + jitter_lng
            lat = center_lat + radius * math.sin(angle) + jitter_lat
            
            points.append((lng, lat))
    
    # 添加时间信息
    pois = []
    current_time = start_time
    
    for i, point in enumerate(points):
        poi = {
            "accuracy": random.uniform(1.0, 3.0),
            "collectTime": current_time,
            "createTime": current_time + 867,
            "index": i + 1,
            "lat": point[1],
            "lng": point[0],
            "offFenceDisM": -1,
            "runTime": i * interval,
            "satellites": random.randint(5, 13),
            "state": 1
        }
        pois.append(poi)
        current_time += interval * 1000
    
    return pois

def generate_pace_list(total_distance, total_time, total_step):
    """生成配速数据"""
    pace_list = []
    pace_interval = 50
    num_segments = int(total_distance // pace_interval)
    
    for i in range(num_segments):
        start_distance = i * pace_interval
        end_distance = (i + 1) * pace_interval if i < num_segments - 1 else total_distance
        
        # 计算时间（假设匀速）
        start_time = int(total_time * (start_distance / total_distance))
        end_time = int(total_time * (end_distance / total_distance))
        
        # 计算步数（假设匀速）
        start_step = int(total_step * (start_distance / total_distance))
        end_step = int(total_step * (end_distance / total_distance))
        
        pace = {
            "endDistance": end_distance,
            "startDistance": start_distance,
            "distance": end_distance - start_distance,
            "endStepCount": end_step,
            "index": i + 1,
            "startTime": start_time,
            "endTime": end_time,
            "time": end_time - start_time,
            "stepCount": end_step - start_step,
            "stability": 0,
            "startStepCount": start_step
        }
        pace_list.append(pace)
    
    return pace_list

def generate_step_list(total_step, total_time, step_interval=20):
    """生成步数数据"""
    step_list = []
    num_segments = int(total_time // step_interval)
    
    for i in range(num_segments):
        start_time = i * step_interval
        end_time = (i + 1) * step_interval if i < num_segments - 1 else total_time
        
        # 计算步数（假设匀速）
        start_step = int(total_step * (start_time / total_time))
        end_step = int(total_step * (end_time / total_time))
        
        step = {
            "endStep": end_step,
            "index": i + 1,
            "startTime": start_time,
            "step": end_step - start_step,
            "endTime": end_time,
            "startStep": start_step,
            "time": end_time - start_time,
            "stability": 0
        }
        step_list.append(step)
    
    return step_list

def generate_stride_list(total_distance, total_step, total_time):
    """生成步幅数据"""
    stride_list = []
    stride_interval = 200
    num_segments = int(total_distance // stride_interval)
    
    for i in range(num_segments):
        stride = {
            "distance": stride_interval if i < num_segments - 1 else total_distance % stride_interval,
            "index": i + 1,
            "time": int(total_time / num_segments),
            "stride": total_distance / total_step * 100,
            "stepCount": int(total_step / num_segments)
        }
        stride_list.append(stride)
    
    return stride_list

def generate_passed_points(target_points, start_time, total_time):
    """生成通过点数据 - 所有点都标记为通过"""
    passed_points = []
    num_points = len(target_points)
    
    if num_points == 0:
        return passed_points
    
    # 计算每个点之间的时间间隔
    interval = total_time / num_points
    
    for i, point in enumerate(target_points):
        # 计算通过时间（从开始时间逐渐增加）
        pass_time = start_time + int((i + 1) * interval * 1000)
        
        passed_point = {
            "code": point.get("code", ""),
            "lng": point.get("lng", 0),
            "lat": point.get("lat", 0),
            "passStatus": True,
            "clockTime": pass_time
        }
        passed_points.append(passed_point)
    
    return passed_points

def get_oss_token():
    """获取OSS上传凭证 - 使用代理"""
    url = "http://api.huachenjie.com/run-front/aliyun/oss/getToken"
    
    headers = {
        "app": "run-front",
        "Authorization": f"Bearer {Authorization}",
        "satoken": satoken,
        "e": "0",
        "v": "oss",
        "pv": "2",
        "User-Agent": UA,
        "api": "aliyun",
        "k": "",
        "Content-Type": "application/json; charset=utf-8",
        "Host": "api.huachenjie.com",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    
    payload = {
        "modelName": modelName,
        "appVersion": appVersion,
        "buildVersion": buildVersion,
        "channel": channel,
        "appCode": appCode,
        "tokenType": "",
        "deviceId": deviceId,
        "systemVersion": systemVersion,
        "platform": platform,
        "timestamp": str(int(time.time() * 1000))
    }
    
    # 使用全局代理设置
    session = requests.Session()
    if proxy:
        session.proxies = {
            "http": proxy,
            "https": proxy
        }
    
    try:
        response = session.post(
            url,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                return data.get("data", {})
    except Exception:
        pass
    
    return None

def upload_face_image_direct(oss_info):
    global face_image_path, proxy
    
    if not oss_info:
        return None
    
    if not os.path.exists(face_image_path):
        # 添加备用路径尝试
        default_path = "/www/wwwroot/yangrun.xyz/3.jpg"
        if os.path.exists(default_path):
            face_image_path = default_path
        else:
            return None
    
    file_ext = os.path.splitext(face_image_path)[1].lower()
    if not file_ext:
        file_ext = ".jpg"

    upload_url = oss_info["domain"]
    access_key_id = oss_info["accessKeyId"]
    access_key_secret = oss_info["accessKeySecret"]
    security_token = oss_info["securityToken"]
    
    parsed_url = urlparse(upload_url)
    host = parsed_url.hostname
    
    bucket_name = "sd-campus-badge"
    
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    server_time = get_server_time()
    if server_time is None:
        server_time = datetime.now(timezone.utc)
    
    max_attempts = 3
    file_url = None
    
    for attempt in range(max_attempts):
        try:
            current_time_millis = int(server_time.timestamp() * 1000) + attempt
            
            file_name = f"{oss_info['directory']}/face_{current_time_millis}{file_ext}"
            
            if file_ext in [".jpg", ".jpeg"]:
                content_type = "image/jpeg"
            elif file_ext == ".png":
                content_type = "image/png"
            else:
                content_type = "application/octet-stream"
            
            gmt_format = '%a, %d %b %Y %H:%M:%S GMT'
            gmt_date = server_time.strftime(gmt_format)
            
            canonicalized_resource = f"/{bucket_name}/{file_name}"
            canonicalized_headers = f"x-oss-security-token:{security_token}"
            
            string_to_sign = (
                f"PUT\n"
                f"\n"
                f"{content_type}\n"
                f"{gmt_date}\n"
                f"{canonicalized_headers}\n"
                f"{canonicalized_resource}"
            )
            
            h = hmac.new(
                access_key_secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha1
            )
            signature = base64.b64encode(h.digest()).decode('utf-8')
            auth_header = f"OSS {access_key_id}:{signature}"
            
            with open(face_image_path, "rb") as f:
                file_content = f.read()
            
            path = f"/{file_name}"
            
            conn = http.client.HTTPSConnection(host, context=context, timeout=30)
            
            headers = {
                "Authorization": auth_header,
                "x-oss-security-token": security_token,
                "Content-Type": content_type,
                "Date": gmt_date,
                "Host": host,
                "Content-Length": str(len(file_content))
            }
            
            conn.request("PUT", path, body=file_content, headers=headers)
            
            response = conn.getresponse()
            status = response.status
            data = response.read()
            
            if status == 200:
                file_url = f"{upload_url}/{file_name}"
                return file_url
            
            server_time = server_time + timedelta(milliseconds=1)
        
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    
    return None

def get_server_time():
    global proxy
    
    try:
        # 配置代理
        proxies = None
        if proxy:
            proxy_url = proxy
            if "://" in proxy_url and ":" not in proxy_url.split("//")[1]:
                proxy_url += ":80"
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
        
        # 发送HEAD请求获取服务器时间
        response = requests.head(
            "http://api.huachenjie.com",
            proxies=proxies,
            timeout=5,
            verify=False
        )
        
        if response.status_code != 200:
            return None
            
        if 'Date' in response.headers:
            date_str = response.headers['Date']
            server_time = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S GMT')
            server_time = server_time.replace(tzinfo=timezone.utc)
            return server_time
        else:
            return None
    except Exception:
        return None
    
def main_wrapper():
    """主函数包装器 - 修改为支持活动跑"""
    global proxy, face_image_path, Authorization, satoken, deviceId
    global selected_run_plan_code, selected_fence_code, selected_semester_code, activity_run_code
    
    # 默认参数
    callback_url = "http://yangrun.xyz/update_order_status.php"
    orderid = None
    status = 3
    remark = ""
    error_code = 0
    params = {}
    
    try:
        # 检查参数
        if len(sys.argv) > 1:
            # 第一个参数是JSON字符串
            try:
                params = json.loads(sys.argv[1])
                
                # 设置代理
                if 'proxy' in params:
                    proxy = params['proxy']
                else:
                    proxy = "http://121.40.95.86"
                
                # 设置人脸图片路径
                if 'face_image_path' in params:
                    face_image_path = params['face_image_path']
                
                # 设置订单ID - 优先使用JSON中的order_number
                if 'order_number' in params:
                    orderid = params['order_number']
                elif len(sys.argv) > 2:
                    orderid = sys.argv[2]
                else:
                    remark = "未找到订单号参数"
                
                # 设置认证信息
                if 'auth_token' in params:
                    Authorization = params['auth_token']
                
                if 'satoken' in params:
                    satoken = params['satoken']
                
                if 'device_id' in params:
                    deviceId = params['device_id']
                
                # 设置围栏代码（仍然需要）
                if 'fence_code' in params:
                    selected_fence_code = params['fence_code']
                
                if 'semester_code' in params:
                    selected_semester_code = params['semester_code']
                    
                # 注意：忽略跑步计划代码，因为我们将使用活动代码
                    
            except Exception as e:
                remark = f"参数解析失败: {str(e)}"
                proxy = "http://121.40.95.86"
        else:
            proxy = "http://121.40.95.86"
            remark = "未提供任何参数"
        
        # 执行主函数，传递 params，并获取执行结果
        success, result_message = main(params)
        
        if success:
            status = 2
            remark = result_message
        else:
            status = 3
            remark = result_message
        
    except AuthExpiredException as auth_ex:
        status = 3
        error_code = auth_ex.error_code
        remark = f"授权失效: {auth_ex.message}"
        
    except Exception as e:
        remark = f"全局异常: {str(e)}"
        status = 3
        
    finally:
        # 确保无论成功还是失败，都尝试回调更新状态
        if orderid:
            try:
                callback_params = {
                    'orderid': orderid,
                    'status': status,
                    'remark': remark,
                    'error_code': error_code
                }
                
                # 发送回调请求，不使用代理
                no_proxy_session = requests.Session()
                no_proxy_session.trust_env = False
                
                response = no_proxy_session.get(callback_url, params=callback_params, timeout=10)
                
            except Exception:
                pass

def main(params=None):
    """主函数：执行完整的活动跑流程"""
    global Authorization, satoken, deviceId, selected_fence_code, selected_run_plan_code, activity_run_code
    
    # 1. 获取进行中的活动
    print("正在查找进行中的活动跑...")
    activity = get_ongoing_activity()
    activity_code = None
    activity_name = None
    
    if activity:
        activity_code = activity.get('sunRunActivityCode')
        activity_name = activity.get('activityName')
        print(f"找到活动: {activity_name}, 代码: {activity_code}")
    else:
        print("没有找到进行中的活动跑，将执行普通阳光跑")
    
    # 2. 获取跑步计划
    plans_data = get_plans()
    if not plans_data:
        return False, "获取跑步计划失败"
    
    plan_list = plans_data.get("list", [])
    if not plan_list:
        return False, "没有可用的跑步计划"
    
    # 使用前端指定的计划或第一个计划
    if selected_run_plan_code:
        selected_plan = None
        for plan in plan_list:
            if plan.get("runPlanCode") == selected_run_plan_code:
                selected_plan = plan
                break
        
        if not selected_plan:
            return False, f"找不到指定的跑步计划: {selected_run_plan_code}"
    else:
        selected_plan = plan_list[0]
    
    run_plan_code = selected_plan.get("runPlanCode")
    school_code = plans_data.get("schoolCode")
    
    # 3. 获取学校围栏
    fences_data = get_school_fences(school_code)
    if not fences_data:
        return False, "获取学校围栏失败"

    # 使用前端指定的围栏或随机选择一个围栏
    if selected_fence_code:
        selected_fence = None
        for fence in fences_data:
            if fence.get("fenceCode") == selected_fence_code:
                selected_fence = fence
                break
    
        if not selected_fence:
            selected_fence = random.choice(fences_data)
    else:
        selected_fence = random.choice(fences_data)
    
    fence_code = selected_fence.get("fenceCode")
    fence_center_lat = selected_fence.get("lat")
    fence_center_lng = selected_fence.get("lng")
    
    # 4. 检查是否有未完成的跑步记录
    unfinished_run_code = query_unfinish_run()
    if unfinished_run_code:
        print("发现未完成的跑步记录，正在强制结束...")
        force_finish_run(unfinished_run_code, fence_center_lat, fence_center_lng)

    # 5. 开始跑步（同时传入跑步计划代码和活动代码）
    print("开始跑步...")
    start_data = start_activity_run(run_plan_code, activity_code, fence_code, school_code, fence_center_lat, fence_center_lng)
    
    # 检查start_data是否是错误响应
    if isinstance(start_data, dict) and "error" in start_data:
        return False, start_data["error"]
    
    if not start_data:
        return False, "开始跑步失败"
    
    run_record_code = start_data.get("runRecordCode")
    target_points = start_data.get("targetPoints", [])
    
    # 6. 模拟跑步数据并上传
    # 设置跑步参数 - 从params获取或使用默认值
    total_distance = float(params.get('distance', 3000)) if params else 3000
    total_time = int(params.get('duration', 786)) if params else 786
    total_step = int(params.get('total_step', 1894)) if params else 1894

    # 获取轨迹点参数
    trajectory_points_str = params.get('trajectory_points') if params else None
    
    # 生成时间戳
    current_timestamp = str(int(time.time() * 1000))
    start_time = int(time.time() * 1000) - total_time * 1000
    
    # 生成更真实的轨迹点，无点数限制
    pois = generate_realistic_pois(
        fence_center_lat, 
        fence_center_lng, 
        start_time,
        trajectory_points=trajectory_points_str,
        target_points=target_points
    )
    
    # 生成配速数据
    pace_list = generate_pace_list(total_distance, total_time, total_step)
    
    # 生成步数数据
    step_list = generate_step_list(total_step, total_time)
    
    # 生成步幅数据
    stride_list = generate_stride_list(total_distance, total_step, total_time)
    
    # 生成通过点数据 - 所有点都标记为通过
    passed_points = generate_passed_points(target_points, start_time, total_time)
    
    # 分批次上传所有轨迹点
    print("上传轨迹点...")
    upload_all_pois_in_batches(run_record_code, pois, batch_size=50)
    
    upload_pass_point(run_record_code, passed_points, current_timestamp)
    upload_pace_record(run_record_code, pace_list, current_timestamp)
    upload_steps_record(run_record_code, step_list, current_timestamp)
    upload_stride_record(run_record_code, stride_list, current_timestamp)
    
    # 7. 尝试上传人脸识别（如果有）
    face_url = None
    if face_image_path and os.path.exists(face_image_path):
        print("上传人脸识别...")
        oss_info = get_oss_token()
        if oss_info:
            face_url = upload_face_image_direct(oss_info)
    
    # 8. 完成跑步
    print("完成跑步...")
    finish_response = finish_sunrun(
        run_record_code, 
        total_distance, 
        total_step, 
        total_time, 
        pois[-10:],
        pace_list,
        step_list,
        passed_points,
        current_timestamp,
        face_url
    )
    
    # 检查完成跑步的响应
    if finish_response and finish_response.get("success"):
        if activity_name:
            return True, f"活动跑执行成功: {activity_name}"
        else:
            return True, "阳光跑执行成功"
    else:
        error_msg = finish_response.get("message", "完成跑步时出现错误") if finish_response else "完成跑步请求无响应"
        return False, error_msg

if __name__ == "__main__":
    main_wrapper()