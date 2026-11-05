# 自动测试模板（尚未启用）

当前GitHub CLI的OAuth授权没有workflow权限，GitHub拒绝创建`.github/workflows/checks.yml`。因此将配置保存为[foundation-checks.yml.template](foundation-checks.yml.template)，不声明已运行远程CI。

本地已验证的命令：

```text
python -m unittest discover -s tests -v
python -m courtsense --output artifacts/new-ci-preview
```

以后获得允许管理workflow的授权后，可将模板复制到`.github/workflows/checks.yml`，提交并查看Actions结果。模板计划在Python 3.10和3.12上验证；这两个远程环境尚未实测。启用前复核Action版本与仓库策略。
