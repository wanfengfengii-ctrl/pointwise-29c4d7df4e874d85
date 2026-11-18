# 港机振动资料中心

海岬港东作业区 07 号岸桥的试验员用便携仪离线采样。日班先登记原始计数并试读，再由巡检员选定波形修订、事件窗、通道校准和速度分量限值。夜班凭交班号读回异常点与整窗摘要。次日补录推进波形当前指针，原修订、原来件回执和已签发包可继续复查。

## 运行

在项目根目录运行以下命令。使用 Python 3.11 标准库与 SQLite，无需安装依赖。

```sh
python3 -B -m unittest discover -s tests
python3 -B -m handoff.workspace demo examples/q07.json
```

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

## 数据路径

`intake/` 校验来件并按完整内容判定重放。`archive/` 保存不可变修订与原始计数块，维护当前指针和事务边界。`windows/` 负责块接续、半开区间和全局时间轴。`quality/` 用固定校准和精确限值生成整窗结论。`handoff/` 原子保存编号与物化报告，负责重开、读回和导出。回归使用临时磁盘库，数据库写入失败场景由实际 SQLite 触发器触发。
