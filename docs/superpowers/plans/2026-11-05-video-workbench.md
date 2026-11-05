# 视频工作台实现计划与共享契约

用户已授权迁入相关姿态基础、通过多智能体实现GitHub任务、3D预览、公开视频监测和报告。默认入口面向RDK，真实性按实测平台记录；不冒称已在板运行。原项目及相机服务不修改。

## 本轮范围

P0.1：原有姿态观察/骨架工具经溯源迁入；默认读取既有RDK HTTP服务，不另开MIPI；可选本地视频适配使用Ultralytics COCO17；标准库HTTP工作台显示视频、真实观察、3D球场示意、图像足踝分布与报告。未标定不显示球场跑图，不造扣杀、球速、综合评分。公开视频仅本地非商业研究验证，不上传视频/抽帧。

## 文件所有权

- pose agent: courtsense/pose/*, courtsense/sources/rdk.py, tests/test_pose*、test_rdk*、docs/migration.md、THIRD_PARTY_NOTICES.md、licenses/*。
- video agent: courtsense/video.py, courtsense/report.py, tests/test_video*、test_report*、requirements-video.txt。
- UI agent: courtsense/web/*（独立HTML/CSS/JS，无CDN，无第三方运行库）。
- root: courtsense/monitor.py与CLI集成、依赖准备、真实公开视频回放验证、README与部署/验收说明、最终集成测试。

## 公共数据契约

RDK适配类 `RDKSource(base_url, timeout=3)`，`read()` 返回 `{observation: 原观察字典, jpeg: bytes}`；配对须核对frame_id、image_space_id、service_instance_id，不一致重试且不得静默混配。原观察结构people列表含keypoints字典(index,name,x,y,probability,valid,reason)、angles_2d、detection_index、track_id可空；顶层width,height,image_space_id,frame_id,received_monotonic_s,processed_monotonic_s,wall_time_s。

视频函数 `analyze_video(video_path, output_dir, *, model_path, stride=5, max_frames=None, on_update=None, device='cpu')`；output_dir为不存在的新目录。输出 `manifest.json`, `observations.jsonl`, `report.json`, `report.html`, `latest.jpg`；不得复制完整源视频到公开目录。每次回调on_update(state)；返回最终state。源视频时间和处理时间分开，源时间按原视频POS_MSEC或明确标记的FPS回退。只处理本地文件，路径由CLI明确给定，不添加任意HTTP下载。

状态JSON供UI使用（缺项可空，禁止造测量）：

```json
{"session_id":"id","status":"running","source":{"kind":"video","label":"file.mp4","platform":"desktop_validation"},"progress":{"frame_id":0,"video_time_s":0,"processed_frames":0,"total_frames":null},"latest":{"width":0,"height":0,"people":[],"image_space_id":"id","frame_id":0},"summary":{"processed_frames":0,"frames_with_people":0,"person_observations":0,"elapsed_s":0,"angle_stats":{},"ankle_points_image":[]},"capabilities":{"pose":true,"court_calibrated":false,"shuttle":false,"smash_count":false,"speed":false},"errors":[],"frame_url":"/api/frame.jpg","video_url":null}
```

视频YOLO输出概率不能再次sigmoid；为兼容原make_observation的logit输入，先clip并logit，边界点与低置信度仍无效。无关键点的候选不造人。帧序号不是track_id。

UI轮询GET /api/state，GET /api/frame.jpg 显示最近已处理图；GET /api/report.json、/api/report.html导出已完成报告；GET /assets/*为静态资源。GET /api/video为CLI选定的文件（仅视频模式，可支持Range），不接收任意文件路径。离线报告可查看相同指标，UI空态可操作。RDK不能连接时显示离线及错误，不自动切换成演示数据。

RDK监测由root累积报告：建议report模块 `summarize(observations, elapsed_s=0)` 和 `write_report(output_dir, state)`。视频可以在线增量摘要，输出统计不含身份/质量评分。报告区分人数检测与真实运动员身份，不计扣杀。

## 验证与交付

各模块先有能捕获语义错误的测试，再实现。根集成核对默认RDK、视频适配、读取服务不改服务、离线错误、配对拒绝、报告和UI一致。真实公开视频本地推理验证要记录来源、许可限制、源哈希、时间段、模型、样本量与平台；无参考不报精度。最终新鲜审查后普通提交推送，更新版本与交接。
