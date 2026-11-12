# Deployment tools / 部署工具

**[← 返回中文 README](../README.md)** · **[← Back to English README](../README.en.md)**

[English deployment guide](../docs/DEPLOYMENT.md) · [中文部署指南](../docs/DEPLOYMENT.zh-CN.md)

For a fresh installation, follow the Docker Compose steps in the guide. To upgrade an existing Ubuntu systemd service, build a release with `build/make_release.py`, extract the archive on the host, then give the upgrade script the extracted directory.

新装系统时，按指南中的 Docker Compose 步骤操作。升级已有的 Ubuntu systemd 服务时，先用 `build/make_release.py` 打包，在主机上解压后，把解压得到的发布目录交给升级脚本。
