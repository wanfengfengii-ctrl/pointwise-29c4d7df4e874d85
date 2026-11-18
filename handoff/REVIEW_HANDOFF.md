# 夜班复查清单交接说明

本说明描述 `publish_review_plan` / `read_review_plan` / `export_review_plan`
三条新接口如何与既有 V1 交班链衔接。日班接口、旧库表、历史成果与全部原回归
均未改动；复查链只新增 `handoff/review/` 子包和三张表。

## 1. 候选身份如何确定

复查只信任**已签发的交班报告**，不直接扫描原始波形。

1. `publish_review_plan(plan_id, shift_ids, max_segments, max_samples)` 先在
   同一写事务内逐个读取 `shift_bindings` 中每个来源号的固定绑定
   （`handoff/review/publish.py::_load_source_bindings`）。来源号合法但未签发
   抛 `KeyError`；来源容器类型非法、为空或含重复抛 `ValueError`。
2. 合并资格按绑定的三项身份比较：固定波形修订号、固定校准修订号、精确上下限
   （`LimitBand` 以 `Fraction` 精确比较，等价分数如 `1/2` 与 `2/4` 视为同口径）。
   窗口范围不参与身份比较，可以重叠或分离。任一来源身份不同即抛 `ValueError`，
   事务回滚，不留编号绑定。
3. 候选只取各来源物化报告（`shift_reports`）里 `high` 与 `low` 异常的全局零基
   下标，在该固定波形上做集合并去重（`collect_candidates`）。原始波形上的其他
   越限点若未被任何已签发报告记录，不取得候选资格。

## 2. 规范见证：三级裁决如何落地

纯函数 `handoff/review/selection.py::select_segments(candidates, K, B)` 不触碰
数据库，输入候选下标集合与两项额度，输出 `(segments, covered_indices, total_samples)`。

- 每个区间 `[lo, hi)` 正长度，`lo`、`hi-1` 都是候选；区间按起点升序、互不重叠、
  可相邻、可跨越无候选的来源窗间隙。
- 读点数为各段 `hi-lo` 之和，段内正常点同样计入读点额度，但只有候选下标计入覆盖。
- 动态规划为带读点预算的前缀背包：`dp[k][j][s]` 保存“前 j 个候选、至多 k 段、
  恰好 s 次读点”下覆盖最多（同覆盖取字典序最小段序列）的方案。对候选 `j-1`
  要么跳过（继承 `dp[k][j-1]`），要么把以其为末候选的新区间挂到 `dp[k-1][i-1]`
  之后，天然保证不重叠。最后在所有可行 `s` 上按
  “覆盖最大 → 读点最少 → 段序列字典序最小”裁决（`_better`）。
- 零预算或无候选直接签发空清单（空段、空覆盖、读点为零）。

`review_cases.py audit` 内置五个手工核账见证（覆盖优先、为全覆盖多读、间隙读点
不算覆盖、预算舍弃远端候选、相邻双段字典序）和三个空结果见证，每个都附纸面
裁决说明；另有 2000+ 组随机用例在开发期对照穷举 oracle 验证（oracle 按同三级
规则枚举全部合法段序列），固定用例沉淀在 `tests/test_review.py`。

## 3. 原子保存与重开复读

- 三张新表（`handoff/review/bindings.py`、`reports.py`）：
  - `review_reports`：物化裁决 JSON（段、覆盖、读点数），与 `shift_reports` 同构；
  - `review_plans`：清单号主键、固定波形/校准修订、十六进制精确限值、两项额度、
    唯一报告外键，带额度非负 CHECK；
  - `review_plan_sources`：清单到来源号的多对多绑定，按 `ordinal` 保存升序来源。
- 整个签发在 `write_transaction` 的 `BEGIN IMMEDIATE` 事务内完成：先查重放，再选段，
  最后先插报告再插绑定与来源行。任一写入失败（测试用真实 SQLite 触发器注入，
  见 `tests/test_review.py::test_atomic_failure_and_same_id_retry` 与
  `review_cases.py::audit_persistence`）整体回滚，无孤儿报告、无编号绑定，
  先前成果不受影响，原清单号可重试成功。
- 同号同绑定（来源集合与两项额度一致，顺序无关）直接读回已物化裁决，不重做选段；
  同号异绑定抛 `ValueError`。
- 读回与导出只走保存结果：`read_review_plan` 还原 dict，`export_review_plan`
  经共享的确定性编码器 `handoff/jsonio.py` 输出 JSON；限值为
  `{numerator, denominator}`，同一清单反复导出逐字节相同，重开档案、补录新波形
  修订或来源更正均不改变已签发清单。
- 复读使用清单返回的固定波形修订号与段区间调用既有 `read_window`，因此补录同名
  全零波形后，原修订上的段计数保持不变（见 `review_cases.py demo`）。

## 4. 运行入口

- `python3 -B verify.py`：全部 unittest（含原 27 项与新复查链）+ V1 见证 +
  独立核账（含 SQLite 故障注入与同号重试），任一失败以非零状态退出。
- `python3 -B review_cases.py sources`：V1 来源窗签发与异常见证。
- `python3 -B review_cases.py demo`：磁盘工作区上的签发、反序重放、补录、重开、
  旧交班导出稳定性与固定修订复读。
- `python3 -B review_cases.py audit`：输出三级裁决与持久化核账 JSON 台账。
- 原 `python3 -B -m handoff.workspace demo examples/q07.json` 保持可用。
