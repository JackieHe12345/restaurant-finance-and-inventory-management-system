# V1.0.2 release status / 发布状态

Version: **v1.0.2**. Date: **2026 Nov 10**. Build revision: **20261110-analytics-english-final**.

The preceding `main` commit `9ab90f8c546c33ebe5443fe57dbcc775148474e7` (Nov07 V1.0.1) is preserved as `old/V1.0.1`. The new release belongs on `main` with commit message `V1.0.2`.

**已部署并通过核验 / Deployed and verified.** Verification completed at `2026-11-10T16:04:19.027042+00:00` (Nov 11 in Asia/Shanghai; the requested release name/date remains Nov 10 V1.0.2).

新修订已上线。公网 38 个网页资源逐一匹配发布包哈希；业务记录、账户、权限、时间记录和运行配置在升级前后保持一致。临时写入限制已解除，服务健康。升级前已创建并验证数据库备份，并保留程序回退副本。实际地址、业务数量和备份路径不进入本仓库。

All 38 publicly served web assets match the release hashes. Business records, accounts, permissions, timing records and runtime configuration passed before/after preservation checks. Temporary write gates were removed and the service is healthy. A fresh database backup was validated and program rollback copies were retained. Private host identities, business counts and backup paths are intentionally omitted.

See [the sanitized deployment verification](acceptance/Nov10Final/deployment-verification.public.json). Earlier package-time notes describe the ZIP as not yet deployed; this status document records the subsequent authorized deployment.

Server bundle SHA-256: `b45544b1409f61317dadefc7a1ae3c947b7873794c10cc1c2fd874e1483d8086`.

Only software, generic documentation and synthetic/sanitized evidence belong in this repository. The owner ZIP, production snapshots, SSH/merchant keys, original server identities and runtime environment values are excluded.
