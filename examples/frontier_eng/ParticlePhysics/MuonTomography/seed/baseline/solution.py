import json
import math
from pathlib import Path

# EVOLVE-BLOCK-START
# ==========================================
# 物理与目标常数定义
# ==========================================
P_ROI = (0.0, 0.0, 30.0)  # 密室的中心坐标 (x, y, z)

def calculate_pointing_angles(x, y, z):
    """
    计算探测器面板的欧拉角 (theta, phi)，使其完美对准 ROI。
    """
    # 计算从探测器指向 ROI 的向量
    dx = P_ROI[0] - x
    dy = P_ROI[1] - y
    dz = P_ROI[2] - z
    
    # 计算距离
    distance = math.sqrt(dx**2 + dy**2 + dz**2)
    
    if distance == 0:
        return 0.0, 0.0
        
    # 计算天顶角 theta (与 Z 轴的夹角)
    theta_rad = math.acos(dz / distance)
    theta_deg = math.degrees(theta_rad)
    
    # 计算方位角 phi (在 XY 平面上的投影与 X 轴的夹角)
    phi_rad = math.atan2(dy, dx)
    phi_deg = math.degrees(phi_rad)
    
    # 确保 phi 在 0 到 360 度之间
    if phi_deg < 0:
        phi_deg += 360.0
        
    return theta_deg, phi_deg

def generate_baseline():
    """
    生成基线解答：在金字塔周围对称布置 4 个探测器，并瞄准 ROI。
    """
    detectors = []
    
    # 我们选择把探测器放在金字塔外部的浅层地下 (z = -5.0)，避免穿模惩罚
    # 放置在 4 个对称的方位：东、南、西、北
    positions = [
        (60.0, 0.0, -5.0),
        (-60.0, 0.0, -5.0),
        (0.0, 60.0, -5.0),
        (0.0, -60.0, -5.0)
    ]
    
    for x, y, z in positions:
        theta, phi = calculate_pointing_angles(x, y, z)
        detectors.append({
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "theta": float(theta),
            "phi": float(phi)
        })
        
    return {"detectors": detectors}
# EVOLVE-BLOCK-END


def _output_path() -> Path:
    # frontier_eval evaluates candidates from a temporary working directory,
    # so the contract is to always write `solution.json` in the current cwd.
    return Path("solution.json")

if __name__ == "__main__":
    # 1. 生成数据
    solution_data = generate_baseline()
    
    # 2. 确定输出路径（保存在当前工作目录下）
    output_path = _output_path()
    
    # 3. 写入 JSON 文件
    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(solution_data, f, indent=2)
        print(f"Baseline solution successfully generated: {output_path.as_posix()}")
        print(f"Total detectors placed: {len(solution_data['detectors'])}")
    except Exception as e:
        print(f"Failed to generate baseline solution: {str(e)}")
