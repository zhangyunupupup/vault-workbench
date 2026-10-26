"""Compose the independently checked body and panel scopes; no STL edits."""
from copy import deepcopy

# The facade rear seats on the box front at source Y=71.90002441.
# Shift the moving group outwards .2 mm to clear the shell mouth at Y=72.000098.
FRONT_Y = 71.90002441
AXIS_HEIGHT = 18.5
CLOSED_OFFSET = .2
PROFILE_ID = 's3-1f-facade-motion-v1'


def facade_joints(body_profiles, panel_profiles):
    body = next((p for p in body_profiles if p['id'] == 's3-1f-body-runners-v1'), None)
    panel = next((p for p in panel_profiles if p['id'] == 's1f-panel-key-cap-v1'), None)
    if body is None or panel is None:
        return []
    combined = deepcopy(body)
    for instance in combined['instances']:
        for pose in instance.get('components') or [instance]:
            if pose['explode'][2]:
                pose['position'][2] -= CLOSED_OFFSET
    for instance in deepcopy(panel['instances']):
        x, y, z = instance['position']
        instance['position'] = [x, AXIS_HEIGHT + z, -FRONT_Y - CLOSED_OFFSET - y]
        instance['rotation'][0] -= 90
        instance['explode'] = [0, 0, -50]
        # Label offsets are in world coordinates, unlike the composed poses.
        instance['label_offset'] = [0, 10, -5]
        combined['instances'].append(instance)
    combined.update({
        'id': PROFILE_ID, 'title': '带前面板抽拉', 'page': 6,
        'note': '九件联动查看，收回参考位置比主体单独视图外移0.2 mm以避开外壳口沿。未包含弹簧、限位、五金、孔盖和标签；旋钮保持固定姿态，不模拟锁定。打印文件保持原样。',
        'method': '面板背面贴合内抽前端面；两侧螺丝孔轴线对齐。将已核对三件面板子装配整体转向并与内抽同步移动，在0–50 mm展示范围做离散截面检查。',
        'instructions': ['按第6页将前面板固定到内抽，旋钮安装方向须对照官方图中的打开状态。此视图不模拟齿轮锁定或弹簧变形。',
                         '内抽、两根内滑轨、前面板、旋钮与盖同步移动；外导轨和外壳固定。0 mm为本视图收回参考位置，50 mm为已采样的展示范围，不是最大行程。',
                         '收回参考位置整组外移0.2 mm，为面板背面与外壳口沿保留约0.1 mm几何间隙；这不是官方公差尺寸。',
                         '预览沿用侧槽支撑清理状态。弹簧、限位块、螺丝、面板孔盖及标签尚未并入，不能当作完整安装清单；打印仍按下方整套清单导出原始文件。'],
    })
    return [combined]
