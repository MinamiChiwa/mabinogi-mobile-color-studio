# 发布指南（维护者）

用户更新方法见[自动更新指南](../automatic-updates.md)。普通代码整理不需要发新版本，也不能覆盖已经发布的同版本资产。

## 发布前核对

- 从包含所需修复的提交构建；确认工作树没有混入日志、用户配置或测试包。
- 同步 `work/studio/build_info.py` 的版本、`release/release-config.json` 的版本/渠道/序号/资产名，以及五语 README 与发行说明。
- 发布序号必须大于线上最高值；不要沿用签名工具的默认值。当前版本以配置文件和已发布清单为准，不在此重复维护版本号。
- 保留现有生产公钥身份。私钥只从仓库外既有位置读取，禁止入库或打印内容。
- 按[测试指南](../../TESTING.md)选择受影响测试，正式发布再运行发布集合。构建通过不等于实机效果通过。

## 构建与签名

先安装 `requirements-build.txt`，确保 Tesseract 已安装。以下尖括号为要替换的参数，不可原样执行：

```powershell
$env:COLOR_STUDIO_DIST='<输出目录>'
$env:COLOR_STUDIO_UPDATE_PUBLIC_KEYS='<公开公钥 JSON 文件>'
python work/studio/build_release.py
python scripts/build_update_assets.py --package <干净包目录> --out <资产目录> --version <版本> --channel stable --key-file <仓库外私钥文件> --key-id <现有公钥ID> --release-sequence <递增序号> --previous-manifest <上一版签名清单>
python scripts/verify_update_assets.py <资产目录> --package <干净包目录> --public-keys <公开公钥JSON>
python scripts/verify_release.py --help
```

`verify_release.py` 负责冻结包内容检查；按其帮助传入实际包。`smoke_frozen_update.py` 用于运行冻结程序的更新演练。生成增量包需要保留对应正式版本的签名清单和基线；不要清理这些输入。

## 用户包应包含什么

完整包用于首次安装；`UPDATE-ONLY` 只用于已有安装的更新。完整包只附带根目录简中、繁中、英文使用说明，日语、韩语说明通过仓库链接查看；应用界面仍有五语。

开发文档、测试、`docs/`、`work/`、会话、设置、私钥和一次性截图不得进入发布包。第三方许可、OCR 和其他运行依赖必须保留。构建器和校验器会检查这一边界。

更新器只根据签名清单替换或删除属于旧官方包的文件；不得扩大到删除未知文件或用户修改的文档。

## 上传与复验

先确认版本、tag、包名、清单字段、签名一致，再上传完整包、UPDATE-ONLY、增量包、清单与签名。资产齐全后从 GitHub 实际地址验证发现更新、生产公钥验签、升级后版本与用户配置保留，再完成正式发布。

发布说明面向用户写“改了什么、怎么更新”，五语都按条目排版；不要写内部验收次数。未做的实机测试如实记录在开发证据中，不写成通过。
