# Release tooling (maintainers only)

User instructions: [update guide](../automatic-updates.md).
Production CLI sources: [asset builder](../../scripts/build_update_assets.py),
[asset verifier](../../scripts/verify_update_assets.py),
[frozen verifier](../../scripts/verify_release.py).

For 0.4.6, set APP_VERSION, manifest version and package naming to 0.4.6.
The reviewed version, channel, sequence, key ID and filenames are recorded in
[release-config.json](../../release/release-config.json). Match the generated
manifest and assets against this file before publishing.
Use the existing production public key and a release sequence above the published
maximum (0.4.5 is sequence6; 0.4.6 uses sequence7). Always pass version and
sequence explicitly; do not use local signing-helper defaults. Do not rotate
keys merely because the application version changes.

Build from main including the title-bar move/resize fix. Generate incremental
archives against the published signed manifests for both 0.4.5 and the final
corrected 0.4.4 (sequence5). Earlier 0.4.4 revisions use the full offline archive.

## 维护者本地命令

面向用户的完整包只附带根目录的简中、繁中、英文 README；日语、韩语说明及开发资料通过 README 中的仓库链接查看，五语界面保持完整。`docs`、`work`（包括 `_internal/docs`）、`TESTING.md` 与 `RELEASE_NOTES.md` 不进入发布包。打包会清除这些旧输出；冻结包校验、更新资产生成和签名资产校验也会拒绝它们，包含空文档目录的完整包同样不能通过。第三方许可和运行依赖保留。

更新器保留旧文档的历史所有权路径，以便升级时按旧签名清单删除原官方文档；不扩大到删除未知文件或用户修改过的文档。

```powershell
$env:PYTHONPATH='work/studio'
$env:COLOR_STUDIO_UPDATE_PUBLIC_KEYS='<公开 key_id 到 32-byte hex 公钥的 JSON>'
python work/studio/build_release.py
python scripts/build_update_assets.py --package <干净包> --out <资产目录> --version <版本> --channel stable --key-file <外部私钥> --key-id <公钥ID> --release-sequence <递增序号> --previous-manifest <上一版清单>
python scripts/verify_update_assets.py <资产目录> --package <干净包> --public-keys <公钥JSON>
```

公开包不包含签名私钥或测试种子；测试 seed 仅保留测试代码，未由生产导入。正式发布前核对嵌入公钥、所有者清单以及便携包逐文件一致，再将清单/签名和全部 blobs 一次上传到 draft。资产齐全并从 GitHub 复验后才发布。不得发布测试签名演练产物。

Historical migration: 0.4.4 introduced the one-time screenshot default.
0.4.5 preserves the user's explicit post-migration search choice and existing
profile data. Renaming the compatibility identifier atlas to screenshot does
not authorize new memory access or change color settings.
