# RDK优先的视频工作台

## 默认：运行在RDK，读取已有姿态服务

本项目运行目标为RDK X5，默认来源是同机既有姿态HTTP服务。新的读取适配已通过本地HTTP夹具验证；**本版整体尚未在真实RDK上执行验收**。前序服务的历史实跑不等于本版已部署。

在板卡的独立目录克隆本项目，保留原服务及文件。Python 3.10+，只读模式不需安装额外模型：

```text
git clone https://github.com/zengwentao62761/courtsense-badminton.git
cd courtsense-badminton
python3 -m courtsense monitor
```

不带参数的`python3 -m courtsense`也是同一个默认入口。它只GET同机`http://127.0.0.1:8080/observations`及`/frame.jpg`。上游需要具有前序服务的对应接口、标识与COCO17观察结构，具体见[migration.md](migration.md)。不另开MIPI、不修改原服务，不捆绑其官方模型权重；不是对全新空板的一键安装器。

UI默认监听`127.0.0.1:8793`。使用VS Code端口转发8793到电脑，然后打开电脑的`http://127.0.0.1:8793/`。服务仅本机使用，不应直接暴露到公网。上游无法连接时会显示离线；同一配对帧5秒未推进显示停滞，不自动切换成合成数据。

每次运行生成新的`artifacts/monitor-*`。`observations.jsonl`记录实际配对观察，运行中每5秒刷新HTML/JSON摘要，Ctrl+C停止RDK观察后完成报告。持续监测产生的数据需要用户安排存储清理，本版没有自动轮转。读取时间不是相机曝光时间。

## 可选：电脑/云端公开视频适配

此入口用于模型开发验证，不把电脑结果冒充RDK结果。在独立Python环境安装可选依赖：

```text
python -m venv .venv
# 激活环境后：
python -m pip install -r requirements-video.txt
python -m courtsense monitor --source video --video /path/to/authorized.mp4 --model /path/to/yolo11n-pose.pt --stride 5 --max-frames 100 --device cpu
```

模型必须提前显式放到本机；分析函数不自动下载模型。可从Ultralytics官方发布获取COCO17姿态权重，独立核对其许可，见NOTICE。文件路径用你自己的实际路径；包含空格时加引号。CUDA可用环境可显式选择其设备，但本版公开验证使用CPU。不要将此依赖安装指南直接当作RDK ARM模型安装指南。

`stride`按解码源帧抽样，`max-frames`指推理样本数而非源视频帧数。源时间来自解码时间戳，不可靠时明确记录按FPS回退。处理图更新与原视频播放独立，页面不声称二者同步。

## 界面与报告

- 最近处理帧、有效关节点、当前检测对象和肘膝二维投影角。
- 可拖拽/键盘旋转的3D标准球场示意；未标定不放置球员或球迹。
- 最近最多1000个有效足踝图像点；是归一化图像分布，非球场轨迹或停留时间热图。
- HTML/JSON报告记录来源、采样、真实检测与描述统计；视频manifest另记录源与模型哈希及推理设置。

视频JPEG已含基础骨架，RDK JPEG也可能含原服务骨架；“附加关节点图层”只控制前端图层，不能擦除源图内容。JPEG与观察必须核对帧号、图像空间及服务实例后才叠加；竞争更新返回409并等待新配对。

检测人数包含场边人员，同一人会在多帧被计入“人数观察”；没有持续身份跟踪。完整报告包含本机路径和真实观察，发布前需另行检查，不能直接提交公开Git。训练视频和模型不包含在仓库中。

## 当前未完成

本版无自动场线标定、米制跑图、羽毛球检测、扣杀计数、真实球速、球拍/手部评分或云端推理服务。3D球场是几何预览，不是人体三维重建。不要用“待接入”的空态当作检测到零次或零速度。
