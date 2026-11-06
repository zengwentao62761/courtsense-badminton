# 数据与坐标约定草案 v0.1

状态：供标定、设备与事件扩展采用的设计草案。现有姿态接口见迁移和运行指南；P0.2.0手动分析输入已实现，精确字段见[开发指南](analysis-development.md)和[JSON样例](examples/analysis-input.json)。本页其余未来字段尚未作为API实现。

## 坐标与时间

| 空间 | 单位 | 定义及限制 |
| --- | --- | --- |
| image_raw | px | 原视频解码图像，左上角为原点；宽、高及旋转随会话保存 |
| image_undistorted | px | 去畸变后图像，记录内参、裁剪和变换；不能混用原图坐标 |
| court_ground | m | 经现场校准的地面平面，原点近侧左外角，+x向右、+y向远端；z=0 |
| court_3d_estimated | m | 带来源与误差说明的三维估计，不能由地面单应伪造 |

近/远端固定为本场次地图定义，换边不改变坐标轴。必须保存机位与坐标示意及像素变换链。实际标定需定义线条内外边/中心，不得把名义示意模板当作控制点真值。

视频frame_id从0开始，记录解码序号与原始PTS/时间基。变帧率、丢帧和降采样均保留原时间；不以处理帧数除假定FPS计算时间。设备单调时间仅在同一设备时钟域内比较；跨设备/端云耗时要记录时钟同步方法与误差，不直接相减两个未同步的时钟。

分析输出同时保存事件时间、处理完成时间、来源片段和算法版本，禁止把云端结果到达时间当成击球发生时间。

## 测量来源

`observed`、`interpolated`、`predicted`、`manual`分别表示检测观察、插值、预测与人工标记。缺失坐标用null并附reason，不用[0,0]或虚构小数代替。模型score不是经过校准的置信概率，必须记录score_semantics。

一个建议的地面定位记录（字段示例，数值不是实测）：

```json
{
  "schema_version": "0.1-draft",
  "session_id": "example-only",
  "frame_id": 0,
  "video_time_s": 0.0,
  "player_track_id": "p1",
  "coordinate_space": "court_ground",
  "position_m": null,
  "source": "observed",
  "status": "unavailable",
  "reason": "calibration_not_verified",
  "calibration_id": null,
  "model_version": null
}
```

有效地面位置至少关联可追溯calibration_id与支撑脚/位置代理定义。跳起和不清楚的足部接触不能凭框底补地面点。跟踪ID只表示当前轨迹，不当作真实身份。

## 击球与扣杀事件

每事件保存event_id、player_track_id、起止时间、类别、候选/人工确认/拒判状态、视频证据和版本。相邻帧候选先合并为一个击球，确认后的扣杀才能进入“确认次数”；候选数量另列。重新分析同段视频不重复累计到历史统计。

## 轨迹与速度

二维球迹记录image空间、球头/球体点定义与可见性。三维轨迹另存相机位姿、物理假设、拟合残差、约束来源和有效区间。速度标明pixel_per_s或m_per_s，区分segment_average、instantaneous_estimate和launch_estimate。不满足独立验证时不开放km/h输出。

## 热图

按可信位置的实际停留时间累计；有效时间、缺失时间与估计补全时间分开。固定地图区域划分和版本，防止两次训练的不同网格产生不可比热图。

## 三设备记录扩展（设计，尚未实现）

| 记录 | 拟保存字段及语义 |
| --- | --- |
| 共用头 | schema_version、session_id、device_id、sequence、source_clock_id、sample_time、received_time、timestamp_semantics、source_version |
| 时钟映射 | mapping_id、源与目标时钟、偏移/漂移模型、适用时间区间、独立对齐残差；不得跨失效区间直接比较 |
| 底盘 | pose、coordinate_frame、odometry_source、transform_version、motion_state、stop_feedback、visual_relocalization_status |
| 云台 | axis_definition、requested_angle、measured_angle、angle_unit、settled、camera_pose_version、calibration_id |
| IMU | accel、gyro、各自单位/量程、axis_definition、mount_orientation、clock_mapping_id、packet_loss；候选事件另记 |
| 命令与反馈 | command_id、session_id、issued_time、deadline、expected_state、ack_state、actual_state、fault、stopped |
| 训练事件 | event_id、task_id、候选/确认/拒判、时间窗口、video_frame_refs、imu_sample_refs、规则与标定版本 |

空间变换需明确父/子坐标系、方向、单位和生效区间。IMU安装到球拍的变换不提供球拍绝对位置；底盘里程计与云台角度也不自动等于已验证的相机外参。相机或底盘移动后，旧标定不能默认继续有效。

已接收、执行中、实际到位、故障分别记录；原始时间保留，映射时间另存。事件发生时间、判定时间和执行反馈时间独立，未确认或时钟失效的事件不进入精确时序评价。
