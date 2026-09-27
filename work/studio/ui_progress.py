"""Presentation-only progress: counts describe actual work, never fake percentages."""
STAGES={
    'waiting':'等待染色界面','zoom':'识别与缩放','capture':'采集颜色板',
    'align':'对齐采集画面','period':'测量色板周期','stitch':'拼接全局颜色板',
    'export':'保存颜色板','validate':'检查拼图质量','search':'搜索目标颜色',
    'similarity':'计算旋转与缩放','ready':'准备候选方案','position':'移动到目标位置','verify':'复核游戏色码',
}


def progress_text(data):
    title=STAGES.get(data.get('stage'),'正在按目标计算，请稍候。')
    if data.get('total'):title+=f"  {data.get('current',0)}/{data['total']}"
    body=('等待手动进入染色倒计时；F9 可停止。' if data.get('stage')=='waiting' else
          '图像处理中，鼠标暂时不动是正常现象。' if data.get('stage') in ('align','period','stitch','export','validate','search','similarity','ready') else
          '根据图像实测位移校正；F9随时停止。')
    return title,body
