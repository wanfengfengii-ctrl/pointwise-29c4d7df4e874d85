# 港机振动资料中心

海岬港东作业区 07 号岸桥的试验员用便携仪离线采样。日班先登记原始计数并试读，再由巡检员选定波形修订、事件窗、通道校准和速度分量限值。夜班凭交班号读回异常点与整窗摘要。次日补录推进波形当前指针，原修订、原来件回执和已签发包可继续复查。

## 运行

在项目根目录运行以下命令。使用 Python 3.11 标准库与 SQLite，无需安装依赖。

```sh
python3 -B verify.py
python3 -B -m handoff.workspace demo examples/q07.json
python3 -B review_cases.py demo
```

`verify.py` 先运行全部 unittest（原回归与复查链），再执行 V1 见证与独立核账，
任一检查失败即以非零状态退出。`review_cases.py demo` 在磁盘工作区上核对夜班
复查清单的签发、来源反序重放、补录、重开、旧交班导出和固定修订复读；
`review_cases.py audit` 输出三级裁决与持久化核账台账。

demo 读取样例文件，在临时磁盘库接纳 R1、试读开头、登记校准并发布 S1。接纳同名更正 R2 后，它关闭并重开档案，读回原包并用新修订签发 S2，输出两份 JSON。样例原窗口的校准值是 `[0, 1, 3]` mm/s，S1 只有下标 2 越上限，发生于波形起点后 `2/3` 秒。更正窗口的校准值是 `[-1, 1, 2]` mm/s，S2 只有下标 0 越下限。

## Python 接口

```python
from fractions import Fraction
from handoff.workspace import open_workspace
from intake.records import InstrumentRecord

with open_workspace('q07.sqlite3') as workspace:
    revision = workspace.register_raw(
        InstrumentRecord('R1', 'Q07', '垂向', 3, 3, [-2, 0, 4])
    )
    counts = workspace.read_window(revision, 0, 2)
    calibration = workspace.register_calibration('垂向', Fraction(1, 2), 1)
    report = workspace.publish_shift('S1', revision, 0, 3, calibration, 0, 2)
    saved = workspace.read_shift('S1')
    exported = workspace.export_shift('S1')
```

- `open_workspace(path)` 打开或初始化 SQLite 文件。重复打开保留已登记数据。工作区支持 `with`，也可显式调用 `close()`。
- `register_raw(record)` 接受来源号、波形名、通道、正整数采样率、非负整数声明长度及有序整数计数。标识为非空且可编码为 UTF-8 的字符串，按原字符串比较。整数输入为普通 Python `int`，不接受布尔值。非法来件或来源冲突抛 `ValueError`。同来源同内容重放返回首个修订号。不同来源接纳时提交新修订、块、当前指针和回执。`get_head(trace_id)` 返回当前修订号，未知名称抛 `KeyError`。
- `read_window(revision, lo, hi)` 返回按全局采样顺序排列的 `list[int]`。`read_indexed_window` 返回绑定修订和半开边界的 `RawWindow`，各样点有 `index`、`count` 和精确 `seconds`。合法范围为 `0 ≤ lo ≤ hi ≤ N`。空窗合法，越界抛 `ValueError`，未知修订抛 `KeyError`，所请求区间内有残缺或重叠块抛 `archive.raw_blocks.ArchiveIntegrityError`。
- `register_calibration(channel, scale, offset)` 返回固定校准修订号。比例、偏移和限值采用 `int` 或 `Fraction`，非法系数或标识抛 `ValueError`。同一通道可以登记多个独立修订。
- `publish_shift(shift_id, waveform_revision, lo, hi, calibration_revision, lower, upper)` 返回 `ShiftReport`。所选校准通道须匹配波形。`value = count * scale + offset`，只有 `value < lower` 或 `value > upper` 时才记录 `low` 或 `high`。上下限相等合法。摘要包含整窗总点数、异常数和精确极值。空窗两项计数为零、两项极值为 `None`。未知修订抛 `KeyError`。非法窗口、限值、通道或交班号绑定冲突抛 `ValueError`。同号同绑定重放使用已物化报告。签发写入失败时编号及报告一并回滚。
- `read_shift(shift_id)` 读回固定绑定和质控结果。结果可经 `report.binding`、`report.summary` 和 `report.anomalies` 访问。`export_shift(shift_id)` 返回确定性 JSON 字符串，包含固定修订、窗口、限值、异常与摘要。下标及计数是 JSON 整数，时间、限值和物理量以 `numerator` 和 `denominator` 表示，空极值为 `null`。两种入口遇到未知交班号均抛 `KeyError`。

## 夜班复查清单

```python
plan = workspace.publish_review_plan('P1', ['S2', 'S1'], 2, 4)
saved = workspace.read_review_plan('P1')
exported = workspace.export_review_plan('P1')
counts = [
    workspace.read_window(saved['waveform_revision'], lo, hi)
    for lo, hi in saved['segments']
]
```

- `publish_review_plan(plan_id, shift_ids, max_segments, max_samples)` 合并同一波形修订、同一校准修订和同一精确上下限的已签发交班报告；来源接受非空 `list`、`tuple`、`set` 或 `frozenset`，不允许重复，保存为按字符串升序的来源列表。额度为非负普通 `int`（布尔无效）。候选只取这些报告高、低限异常的全局下标并去重。非法容器、口径冲突或同号异绑定抛 `ValueError`；合法但不存在的来源号或清单号抛 `KeyError`。
- 选段为互不重叠、可相邻、可跨来源窗间隙的半开区间，首末样点均为候选。按“覆盖唯一异常点最多 → 总读点最少 → 区间序列字典序最小”裁决，段数与读点数分别受额度约束；零预算或无候选签发空清单。
- 同号同绑定（来源集合与额度一致、顺序无关）重放返回原已保存结果，不重做选段。读回返回包含 `plan_id`、`shift_ids`、固定修订、`limits`（`Fraction`）、额度、`segments`、`covered_indices`、`total_samples` 的 dict；`export_review_plan` 返回确定性 JSON，限值为 `{numerator, denominator}`，同一清单反复导出逐字节相同。
- 签发在单事务内原子写入；写入失败整体回滚、不留下编号绑定，原号可重试。后续来件更正、重开档案都不改变已签发清单，复读始终使用清单固定的波形修订和区间。设计细节见 `handoff/REVIEW_HANDOFF.md`。

## 数据路径

`intake/` 校验来件并按完整内容判定重放。`archive/` 保存不可变修订与原始计数块，维护当前指针和事务边界。`windows/` 负责块接续、半开区间和全局时间轴。`quality/` 用固定校准和精确限值生成整窗结论。`handoff/` 原子保存编号与物化报告，负责重开、读回和导出；`handoff/review/` 在已签发报告之上合并候选、裁决复查区间并原子保存清单。回归使用临时磁盘库，数据库写入失败场景由实际 SQLite 触发器触发。
