import json
import sys
import math
import numpy as np

# ==========================================
# 物理与经济常数定义
# ==========================================
P_ROI = np.array([0.0, 0.0, 30.0])  # 感兴趣区域(密室)中心坐标
DETECTOR_AREA = 1.0                 # 探测器标准面积 A
C_BASE = 20.0                       # 探测器基础造价
DIGGING_COST_RATE = 1.5             # 地下挖掘费率 (/米)
PENALTY_INSIDE = 10000.0            # 违规放置在金字塔内部的巨大惩罚值
EXPOSURE_TIME = 100000.0            # 模拟长时间曝光的信号乘数

def is_inside_pyramid(x, y, z):
    """
    判断探测器是否违规放置在了金字塔内部。
    金字塔底面中心在 (0,0,0)，边长 100，高 100。
    """
    if z < 0 or z > 100:
        return False
    # 在高度 z 处，金字塔截面的半边长
    half_side = 50.0 * (1.0 - z / 100.0)
    # 如果 x 和 y 都在当前高度的截面范围内，则视为在内部
    if abs(x) <= half_side and abs(y) <= half_side:
        return True
    return False

def calculate_signal(detector):
    """
    计算单个探测器接收到的有效缪子信号。
    """
    p_i = np.array([detector.get('x', 0.0), detector.get('y', 0.0), detector.get('z', 0.0)])
    
    # 向量 v: 从探测器指向 ROI (这也是用来计算入射角的正确视线方向)
    v = P_ROI - p_i
    distance = np.linalg.norm(v)
    
    if distance < 1e-5:
        return 0.0
        
    # ROI 必须在探测器的正上方方向 (v_z > 0)
    if v[2] <= 0:
        return 0.0
        
    cos_theta_z = v[2] / distance
    
    # 将探测器的欧拉角 (theta, phi) 转化为法向量 n
    theta_rad = math.radians(detector.get('theta', 0.0))
    phi_rad = math.radians(detector.get('phi', 0.0))
    n_x = math.sin(theta_rad) * math.cos(phi_rad)
    n_y = math.sin(theta_rad) * math.sin(phi_rad)
    n_z = math.cos(theta_rad)
    n = np.array([n_x, n_y, n_z])
    
    # 入射角的余弦值应该是视线方向 v/distance 与 面板法向量 n 的点积
    ray_dir = v / distance
    cos_gamma = np.dot(ray_dir, n)
    
    effective_cos_gamma = max(0.0, cos_gamma)
    
    # 乘以 EXPOSURE_TIME 放大有效信号，以平衡经济成本
    signal = EXPOSURE_TIME * DETECTOR_AREA * (cos_theta_z ** 2) / (distance ** 2) * effective_cos_gamma
    return signal

def evaluate_solution(solution_data):
    """
    主评估函数，处理 JSON 数据并计算最终得分。
    """
    detectors = solution_data.get("detectors", [])
    
    # 限制探测器数量 (最大 15 个)
    if not detectors:
        raise ValueError("Detector list is empty.")
    if len(detectors) > 15:
        raise ValueError("The number of detectors exceeds the limit (max 15).")
        
    total_signal_sum = 0.0
    total_cost = 0.0
    
    for det in detectors:
        # 使用 get 避免 Agent 漏传字段导致 Python 崩溃，默认给 0.0
        x = det.get('x', 0.0)
        y = det.get('y', 0.0)
        z = det.get('z', 0.0)
        
        # 1. 累加信号量
        total_signal_sum += calculate_signal(det)
        
        # 2. 计算经济成本
        cost = C_BASE
        if z < 0:
            cost += DIGGING_COST_RATE * abs(z) # 加上挖掘成本
        if is_inside_pyramid(x, y, z):
            cost += PENALTY_INSIDE # 加上违规穿模惩罚
            
        total_cost += cost
        
    # 3. 计算最终指标 (对数模拟收益递减)
    total_signal_score = 100.0 * math.log1p(total_signal_sum)
    final_score = total_signal_score - total_cost
    
    return {
        "score": float(final_score),
        "status": "success",
        "metrics": {
            "total_signal": float(total_signal_score),
            "total_cost": float(total_cost),
            "valid_detectors": len(detectors)
        }
    }

if __name__ == "__main__":
    # Frontier-Eng 框架会通过命令行参数传入 json 文件的路径
    if len(sys.argv) != 2:
        print(json.dumps({
            "score": 0.0, 
            "status": "error", 
            "message": "Usage: python evaluator.py <path_to_solution.json>"
        }))
        sys.exit(1)
        
    solution_file = sys.argv[1]
    
    try:
        with open(solution_file, 'r') as f:
            solution_data = json.load(f)
            
        result = evaluate_solution(solution_data)
        print(json.dumps(result))
        
    except Exception as e:
        # 如果 Agent 生成的 JSON 格式错误或缺失字段，捕获异常并返回纯英文错误信息
        error_result = {
            "score": 0.0, 
            "status": "error", 
            "message": f"Evaluation failed: {str(e)}"
        }
        print(json.dumps(error_result))