# 旧分支源代码归档

`search_evidence.py` 和 `test_search_evidence.py` 原样保留旧 0.3.6 图像寻色分支的 `RoundEvidence` 行为与测试合同。当前权威源码快照不包含该子系统，其 `confirmed_frame_ids`、`budgeted_candidate_search` 和旧 `round_evidence` Runner 事件未接入当前生产路径。

当前原生寻色使用会话中的结果、观测、checkpoint、输入 receipt 和事件日志记录证据。归档文件用于研究和追溯旧设计，不属于当前生产源代码指纹或 `work/studio` 的默认 `unittest` 发现范围，也不表示当前程序支持旧接口。未修改归档文件内容、未使用无条件跳过掩盖失败。

同样原样归档 `mechanism_experiment.py`、`progressive_atlas_replay.py` 和 `test_mechanism_experiment.py`。它们是旧分支的独立机制实验与 progressive atlas 回放工具，当前权威快照的生产模块、启动入口和测试入口均未引用它们。保留其原始内容便于追溯，不重新接入当前寻色路径。
