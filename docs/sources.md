# 资料与复用边界

以下为设计参考，不是已集成依赖。使用前核对具体版本、许可、权重和数据集的再分发条件；不把“公开可下载”当作可公开上传。

- OpenCV相机标定、投影几何、单应与外参：https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
- TrackNetV3原作者实现：https://github.com/qaz812345/TrackNetV3
- MonoTrack单目羽毛球轨迹研究：https://arxiv.org/abs/2204.01899
- BWF羽毛球规则与场地图：以BWF现行规则核验；官方文档入口 https://system.bwfbadminton.com/documents/folder_1_81/Statutes/CHAPTER-4---RULES-OF-THE-GAME/SECTION%204.1-%20Laws%20of%20Badminton.pdf

本次官方PDF链接未成功完整读取，尺寸与线宽细节应在实现前取得可读的现行原文复核，不把该链接存在视为已完成规则核验。

P0.0.1补充：已读取香港羽毛球总会托管的BWF 2023版规则和Diagram A。当前名义几何示意参考其场地尺寸，仍需在真实标定实现前核对适用的现行版本及线条边缘/中心语义；不将2023版声明为现行规则。

https://hkbadmintonassn.org.hk/wp-content/uploads/2023/06/Section-4.1-Laws-of-Badminton-29-May-2023-V2.0.pdf

已有方法说明这一领域具有成熟研究基础。本项目需要针对本机位、采集质量、可信定位与训练反馈重新验证，不宣称独创SLAM、单目重建或球体跟踪算法。
