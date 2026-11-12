# Deployment Tools / 部署工具

**[← 返回中文 README](../README.md)** · **[← Back to English README](../README.en.md)**

[Deployment Guide](../docs/DEPLOYMENT.md) · [中文部署指南](../docs/DEPLOYMENT.zh-CN.md)

For a new installation, follow the Docker Compose procedure in the Deployment Guide. For an existing Ubuntu service managed by systemd, build the release with `build/make_release.py`, extract the archive on the target host, and pass the extracted directory to the upgrade script.

新建实例时，请按部署指南中的 Docker Compose 步骤安装。升级由 systemd 管理的 Ubuntu 服务时，先用 `build/make_release.py` 生成发布包，在目标主机上解压，再将解压后的发布目录传入升级脚本。
