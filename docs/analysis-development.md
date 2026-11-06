# 标定、跑位、球迹、扣杀与球速开发入口

P0.2.0 · 2026-11-06。五项已接入可运行的手工/导入分析管线及界面，并非仅有占位文字。自动场线提取、球体检测、扣杀分类与三维重建尚未接入；真实球场与RDK整体验收待补。

## 从界面开始

运行 `python -m courtsense monitor`，打开 `http://127.0.0.1:8793/`。若不连接真实来源仍可打开界面，采集区如实保持离线。

1. 进入“标定与跑位”，点击“预览合成样例”。这一步需主动操作，程序不会自动把合成数据装成实时采集。
2. 查看“点对已拟合”、3D球场的接地跑位和独立球迹画布。所有样例结果有合成标识。
3. 编辑JSON点对与记录后点击“应用JSON”，或使用“导入文件”选择下方示例，再应用。
4. 切换“球迹与击球”检查候选/确认事件及速度单位；导出输入用于重现，导出结果用于检查派生值与来源。
5. 点击“清除分析”，分析图层及指标恢复空态，采集服务不受影响。

完整结构示例：[analysis-input.json](examples/analysis-input.json)。示例含人工构造的三维坐标，产生的km/h只验证计算流程，不是实测球速。页面快捷样例只含二维球迹，显示px/s。

若当前来源已有完整真实帧，离线样例只填入编辑器，不覆盖当前来源；另启动一个没有真实帧的开发工作台即可预览。真实来源导入请点击“当前来源模板”，保留生成的绑定字段，再填写对应实际观测。绑定必须与当前来源、会话、服务实例、图像尺寸和图像空间一致。

## 五项模块当前能做什么

| 功能 | 已有开发基础 | 等待接入与实测 |
| --- | --- | --- |
| 球场标定 | 4到64组手动点对求单应矩阵，拒绝重复/退化/明显不一致点对 | 自动场线、独立控制点误差、镜头与现场适用范围 |
| 米制跑图 | 将带contact_confirmed=true的地面像素点映射到米制球场，离地与未确认点断开 | 自动接地判断、身份跟踪、独立位置与距离测量 |
| 羽毛球轨迹 | 导入像素球迹，保留缺失；可另显示有明确来源的三维坐标 | 真实高速小目标检测、多帧关联与三维重建 |
| 扣杀计数 | event_id去重，候选与确认分别统计，冲突记录拒绝 | 自动扣杀分类、人工标签标准和分类效果 |
| 球速 | 相邻有效点按实际时间算px/s；显式三维坐标且来源一致时计算段平均估计m/s、km/h | 三维估计依据、独立测速与离拍初速验证 |

坐标输入约定为已经去畸变的像素。当前工具不执行去畸变，直接输入原镜头畸变坐标无法获得可信空间测量。标准球场示意的线宽/边缘定义仍需真实标定前核对。

标定返回的reprojection_rmse_m只是在用于拟合的控制点上的残差，0.25m是开发阶段的拒绝阈值，不是精度保证。所有结果标为development_unverified；现场另测近、中、远独立控制点后再发布实际精度。

## 导入契约与API

`GET /api/analysis`返回status、当前binding、导入data、派生result及limitations。status为empty、ready或invalidated。`POST /api/analysis`验证完整输入后原子替换；`POST /api/analysis/reset`以空对象清除当前分析。

顶层字段：schema_version=1、mode、source_name、synthetic、image_space；其余可选calibration、player_points、shuttle_points、events。live模式必须附当前GET返回的binding。offline_development用于无当前真实帧的开发，不能附live绑定。

- image_space保存id、width、height、service_instance_id。
- calibration保存input_space=undistorted_pixels和pixel/court_m点对。
- player_points保存t_s、player_id、pixel、contact_confirmed。
- shuttle_points保存t_s、track_id、pixel；缺失pixel为null。可选world3d_m必须同时给world3d_source。
- events保存event_id、t_s、type=smash、status=candidate或confirmed、source。

每条球员/球迹中的时间严格递增；唯一事件按时间输入。同一event_id完全重复时去重，有冲突时拒绝。没有标定的球员点保持court_m=null；球迹不会通过地面单应生成三维或km/h。像素缺失、三维缺失或三维来源切换会断开相关速度段。

每次替换或清除在运行输出目录保存独立analysis-UUID.json，包含输入、结果、绑定和保存时间，不覆盖既有姿态report.json。重新启动不会自动恢复旧分析，需显式重新导入并检查绑定。姿态HTML报告仍是原观察摘要，领域结果另从分析面板导出。

写入仅支持本地同源JSON，最大1MiB；每类记录最多10000条。非有限值、重复JSON键、越界像素和无效坐标会被拒绝；失败保持原分析。以VS Code转发使用同端口本地入口；这些端点不是公网云服务。

## 后续适配

自动场线模块未来生成calibration点对，人体跟踪/接地模块生成player_points，球体检测模块生成shuttle_points，击球分类模块生成events。先保存可追溯输入再交给同一管线计算。移动底盘与云台改变机位后重新校验，球拍IMU提供候选事件窗口；具体见[三设备设计](embodied-expansion.md)。

现有绑定检查可发现软件声明的来源/图像空间变化，不能自行检测未声明的机械位移；不要把它当作已实现视觉机位漂移检测。实时视频与导入事件目前没有统一播放游标，独立分析画布与视频不会伪装为逐帧同步。
