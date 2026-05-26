# 测试设计章节(Test Design)

> 对应模块:`core/testcase_generator.py`、`core/optimizer.py`
> 对应测试:`tests/testcase_generator_test.py`、`tests/optimizer_test.py`

## 1. 设计目标与定位

本部分(B 部分:测试设计引擎)位于工具流水线的中后段。整体数据流为:

```
需求文本 ──A──> 风险分析(risk)   ┐
        └─A──> 覆盖项(coverage) ┼──B──> ① 测试用例生成 ──> ② 测试套件优化
                                  ┘
```

- **A 部分**输出"要测哪些情况":覆盖项(coverage item)只是一句条件描述,例如
  `username already exists`、`password length = 7`,无法直接执行。
- **B 部分**负责把覆盖项转化为**可执行、可追溯、带优先级的结构化测试用例**,
  再依据风险对整套用例进行**排序与最小化**。

设计上刻意采用**确定性规则引擎**(不调用 LLM):相同输入永远得到相同输出,
便于复现、便于在报告中引用、也避免了网络与模型不确定性。

## 2. 输入与输出

### 输入
- 覆盖项 JSON:兼容顶层 key 为 `"coverages"`(A 代码 `generate_coverage()` 的真实输出)
  与 `"coverage"`(样例文件写法)两种形式。
- 风险分析 JSON:读取 `"risk_assessment"` 列表,按 `requirement_id` 建立索引。
  风险信息允许缺省;缺省时默认 `risk_level = "Medium"`、`risk_score = 5`。

### 输出
```json
{
  "test_cases": [ { ...单条测试用例... } ],
  "summary": {
    "total": 19,
    "by_technique": { "Equivalence Partitioning": 6, "Boundary Value Analysis": 7, "Decision Table Testing": 6 },
    "by_priority":  { "Low": 12, "Medium": 7 }
  }
}
```

## 3. 黑盒测试技术及其应用逻辑

引擎根据覆盖项的 `type` 字段自动选择测试设计技术:

| 覆盖项类型 `type` | 选用技术 | 应用逻辑 |
|---|---|---|
| `positive` / `negative` | **等价类划分 Equivalence Partitioning** | 正例代表"有效等价类",负例代表"无效等价类",各取一个代表值即可 |
| `boundary` | **边界值分析 Boundary Value Analysis** | 针对取值范围的临界点(如长度 7/8/9、19/20/21)取值,缺陷最易出现在边界 |
| 同一需求下的多个覆盖项 | **决策表测试 Decision Table Testing** | 把多个条件的组合(全满足 / 缺一个 / 缺多个)作为规则,覆盖条件之间的相互作用 |
| `fallback` / `unknown` | **人工审查 Manual Review** | 无法自动推断时生成占位用例,并置 `need_manual_review = true` |

### 3.1 等价类划分(EP)
对 `positive`/`negative` 覆盖项各生成一条用例。例如覆盖项
`username already exists (negative)` → 用例尝试用已存在用户名注册,期望系统拒绝。

### 3.2 边界值分析(BVA)
对 `boundary` 覆盖项生成用例。结合约束 `password: min 8, max 20`,
对 `length = 7`(越下界)判定为应拒绝,`length = 8`(在界内)判定为应接受;
当引擎无法确知 min/max 时,采用保守表述"应按需求处理该边界值"。

### 3.3 决策表测试(DT)
当一个需求拥有多个覆盖项时,额外生成 1~3 条组合用例:

1. **所有必需条件均满足 → 系统接受**(来自正例集合)
2. **恰好缺少一个必需条件 → 系统拒绝**(来自负例集合)
3. **同时违反多个条件 → 系统拒绝**(负例 ≥ 2 时)

若无法自动推断组合(例如某需求只有边界项、无正/负例),则生成一条基础决策表用例
并标记 `need_manual_review = true`。每个需求最多生成 3 条决策表用例。

## 4. 测试用例结构

每条用例字段统一,便于后续 `exporter` 导出与报告引用:

| 字段 | 说明 |
|---|---|
| `test_case_id` | 稳定可读 ID,格式 `TC-{需求号}-{三位序号}`,如 `TC-R1-001` |
| `requirement_id` / `feature` | 来源需求与功能名 |
| `title` / `description` | 用例标题与说明 |
| `test_design_technique` | 所用黑盒技术 |
| `coverage_item` / `coverage_type` | 来源覆盖项原文与类型(可追溯) |
| `preconditions` / `test_data` / `steps` | 前置条件、测试数据、操作步骤 |
| `expected_result` | 期望结果 |
| `priority` / `risk_level` / `risk_score` | 优先级与风险信息 |
| `traceability` | 追溯块:`source_requirement` / `covered_item` / `coverage_strategy` |
| `review_status` / `need_manual_review` | 生成状态与是否需人工确认 |

## 5. 测试数据生成规则(`infer_test_data`)

依据覆盖项描述中的关键词推断出具体且合理的测试数据(节选):

| 覆盖项描述 | 生成的 test_data |
|---|---|
| `username already exists` | `{"username": "existing_user"}` |
| `username is new unique value` | `{"username": "new_user_001"}` |
| `username is empty` | `{"username": ""}` |
| `password length = 7` | `{"password": "A1bcdef"}`(长度 7,含大写/数字/小写) |
| `password length = 20` | 长度为 20 的合法密码 |
| `missing uppercase` | `{"password": "abc12345"}` |
| `missing lowercase` | `{"password": "ABC12345"}` |
| `missing digit` | `{"password": "Abcdefgh"}` |
| `contains all required` | `{"password": "Abc12345"}` |

规则采用子串匹配,因此对 A 的丰富描述(如 `missing uppercase (has ['lowercase','digit'])`)同样适用。

## 6. 期望结果生成规则(`infer_expected_result`)

- **positive**:系统应接受输入并继续正常流程。
- **negative**:系统应拒绝输入并给出合理错误信息。
- **boundary**:能从描述解析出长度时,结合 8~20 范围判定接受/拒绝;
  否则采用保守表述。
- **fallback / unknown**:期望行为不明确,需人工对照需求审查。

## 7. 风险等级 → 优先级映射

| 风险等级 `risk_level` | 优先级 `priority` |
|---|---|
| High | High |
| Medium | Medium |
| Low | Low |
| (缺失) | 默认 Medium |

该映射在生成用例时即写入每条用例,并在优化阶段保持一致。

## 8. 测试套件优化设计(`optimizer.py`)

### 8.1 优先级排序 `prioritize_test_cases`
按以下次序降序排序(排序稳定,平局保持原序):

```
风险等级(High>Medium>Low) → 风险分(越高越前) → 技术(决策表>边界值>等价类) → 覆盖类型(boundary/negative 优先)
```

### 8.2 基于风险的最小化 `minimize_test_suite(mode="risk_based")`
- **High 风险需求**:保留全部用例(风险越高,覆盖越充分)。
- **Medium 风险需求**:保留每种覆盖类型的代表用例,并保留全部决策表用例。
- **Low 风险需求**:按覆盖类型去重精简,但**每个需求至少保留 1 条**。

### 8.3 统一入口 `optimize_test_suite`
可选地用 `risk_json` 刷新各用例的风险/优先级,然后排序,
再按需最小化,返回:

```json
{
  "optimized_test_cases": [ ... ],
  "optimization_summary": {
    "original_count": 19, "optimized_count": 11,
    "strategy": "risk_based_minimization", "removed_count": 8
  }
}
```

## 9. 验证

`tests/` 下两套单元测试(共 19 个)覆盖:三种技术齐全、ID 格式与唯一性、
可追溯性、风险→优先级映射、fallback 人工审查、空输入容错、排序正确性、
以及"最小化后每个需求至少保留 1 条"。在示例数据上全部通过(OK)。
