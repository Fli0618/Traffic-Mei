# Traffic-Mei · 梅大高速事故现场 Blender 场景

依据用户提供的梅大高速灾后航拍画面，重建道路、连片密林、边坡、路面缺口和滑塌裸土。**项目范围是事故现场的三维视觉还原**；没有边坡牢固程度判断、监测设备、提前预警或风险评分。

## 运行

需要 **Blender 4.5 LTS**。不依赖第三方 Python 包或外部素材。

```bash
blender --background --python build_scene.py -- --output output
```

快速预览（较低分辨率和采样数）：

```bash
blender --background --python build_scene.py -- --output output/draft --draft
```

只生成可编辑工程：

```bash
blender --background --python build_scene.py -- --output output --no-render
```

Windows 用户可以使用 Blender 可执行文件的完整路径代替 `blender`。

## 生成的内容

- `output/meida_accident_scene.blend`：可编辑场景。
- `output/aerial_overview.png`：白天航拍主视角。
- `output/collapse_detail.png`：路面缺口与土坡近景。
- `output/scene_manifest.json`：实际生成的对象、树木数量及参数记录。

工程按地形、道路护栏、密林、塌方、车辆、相机、光照分类。树木使用共享网格实例，树冠由多组不规则叶团和叶片构成；通过树高、冠幅、方向及叶色变化形成连续林冠。道路两侧近路区域、排水设施和塌方区域分别处理植被。

主场景为**白天灾后状态**，用于对齐航拍参考。另有默认关闭的雾体，属于可选视觉效果；不表示事故当晚已证实存在大雾。

## 参考与精度边界

- 主要视觉参考：用户提供的灾后航拍截图。没有将截图本身上传到仓库。
- 地点背景：[广东省政府梅大高速茶阳路段调查评估报告](https://www.gd.gov.cn/attachment/0/571/571268/4659608.pdf)。
- 场景采用局部米制坐标。道路尺寸、弯曲、地形高差、树种及车辆位置是建模近似，**尚未经过 DEM、点云或设计图测绘配准**。
- 航拍画面反映灾后状态，可能包含救援、清理造成的地形变化；不能据此认定为塌方发生瞬间的精确几何形态。
- 车辆仅提供比例参照，不代表真实事故车辆数量或位置。没有添加未经核实的伤亡、火灾、传感器及预警设施。

## 配置

`scene_config.json` 控制随机种子、林木间距及渲染参数。修改后重新运行生成脚本。其他道路和地形形状目前在脚本中参数化定义。

仓库只保存源码与说明，不包含 Blender 安装包、依赖目录或用户其他项目文件。生成的 `.blend` 与渲染图默认忽略，可在本地复现。
