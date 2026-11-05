# finreport-global

[English](README.md) | 简体中文

**海外友商财务数据引擎**：取境外上市公司的收入、毛利、毛利率——两个独立结构化数据源互相交叉核对、非自然年财年自动映射、期间平均汇率换算、字段级来源审计——统一标准化为千美元。

[finreport-cli](https://github.com/ryangucheng2022-sudo/finreport-cli)（A 股财报）的姊妹篇。剥离自一套生产运行中的友商财报监控系统。

## 工作方式

```
watchlist.json ──► fetch ──► 东方财富美股 F10（主源，结构化）
                      ├──► MSN Finance（交叉核对／回退）
                      ├──► 官网月度披露（按公司 playbook，如矽力杰）
                      └──► 经复核 CSV（最后兜底）
                           │
                           ▼
              标准化 CSV（千美元）＋审计 JSON
              （每个数值都带来源层级与证据）
```

- **来源优先级**：东方财富 F10 → MSN → 官网／正式公告 → 经复核 CSV。两源差异超容差即标 `needs_review`，绝不静默取平均。
- **财年映射**：英飞凌（财年 9 月末）、ADI、微芯等公司的财季与自然季度不对齐，`fiscal_calendar.py` 把东方财富报告期 token 与 MSN 财季统一映射到真实期间，输出自带实际起止日期。
- **汇率**：非美元金额按期间平均汇率换算——EUR/JPY/CNY 用 ECB 日度参考汇率、TWD 用台湾央行银行间市场数据，原始汇率证据随结果留档。
- **未披露就是未披露**：任何来源都没有正式披露的期间，行内明示；预告、指引、预测一律不顶替。

## 方法

- **主数据源**：东方财富美股 F10 提供结构化的收入与毛利数据，是友商表格的工作数据源。
- **交叉核对，而非盲信**：同一期间的数据与 MSN Finance 比对；主源缺期时以 MSN 回退。两源不一致的在产出中明示，不静默取平均抹平。
- **财年映射**：按公司逐一建立财年与自然年的映射（6 月结束的「FY2026」不等于自然年 2026），映射是仓库里的显式数据，不是代码里的假设。
- **归一化**：收入与毛利润按带日期的汇率统一折算为千美元口径，保证同表内每家公司的单位与期间定义一致，然后才谈对比与排名。
- **校验**：组表前有逐公司的明细复核，把采集值与来源计划再对一遍。

## 命令

```bash
# 结构化取数：2026 H1 vs 2025 H1（fetch 支持 06-30 与 12-31 目标期）
bin/finreport-global fetch --target 2026-06-30 --compare 2025-06-30 \
  --output out.csv --raw-dir raw/ --audit-json audit.json

bin/finreport-global plan    --year 2026 --period-type quarter --period 3 --output plan.csv
bin/finreport-global auto    --year 2026 --period-type quarter --period 3 --output candidates.csv
bin/finreport-global monitor --normalized-csv reviewed.csv --year 2026 \
  --period-type quarter --period 3 --output-dir monitor-out/
bin/finreport-global template  --output raw-template.csv
bin/finreport-global normalize --input raw.csv --output normalized.csv
bin/finreport-global detail-template  --output detail-template.csv
bin/finreport-global detail-validate  --input detail.csv
```

- `plan`／`auto`：生成官方来源检索计划，并从公司 IR／公告页抽取收入候选。
- `monitor`：按已复核的标准化 CSV 复查官方来源、只报变化，绝不自动覆盖已复核值。
- `normalize`：把本币收入按期间平均汇率标准化为千美元。

## 配置

名单是**配置不是代码**：`config/watchlist.json`（随包附 10 家半导体样例 `watchlist.example.json`）。每家含东方财富证券代码、法定名、报告币种、财年说明、IR 主域名与检索模板，按同样格式加你自己的公司即可；个别公司的特殊路径（如矽力杰官网月度收入公告，TWD/USD 双列）在 `docs/` 的 playbook 里。

## 谁在用、用它做什么

| 角色 | 典型场景 | 价值点 |
|---|---|---|
| **跨境投研人员** | 每个财报季跟踪美/欧/日/台上市友商 | 每个数字双源核对、财年期间真实对齐、一张千美元表直接可比 |
| **战略与竞争情报** | 全球友商对标、董事会材料 | 数字可审计：每个值注明来源层级；未披露明示不估算 |
| **财务数据工程师** | 搭一条可重复的海外财报数据管道 | 原始响应归档、汇率证据留存、异常进 `needs_review` 队列而不是静默坏数；为增量重跑而设计 |
| **Agent 开发者** | 让 AI Agent 去采集友商财报 | 确定性 CLI＋JSON 审计；来源冲突如实上报，不靠幻觉填平 |

## 关于 MSN_API_KEY

MSN Finance 调用使用其网页端随页面公开下发的客户端 key。本包**不内置**该 key：通过环境变量 `MSN_API_KEY` 注入。未设置时引擎以东方财富 F10 为主源运行（加官网／复核兜底），并在审计里如实记录未启用 MSN；样例名单中有两家（英飞凌、瑞萨）在 F10 无覆盖、以 MSN 为主路线，需要它们时请设置 key。

## 数据源声明

东方财富 F10 与 MSN Finance 均为公开网页接口、非官方开放 API，可能随时变动。本项目仅供研究与内部分析使用，请遵守来源方使用条款。数据质量取决于底层披露，审计留痕就是为了让你能复核。

## 数据源契约

两个上游的响应结构由 `tests/fixtures/` 下的脱敏 fixture 钉住，并经 `tests/test_schema_drift.py` 用真实解析函数跑过：东方财富或 MSN 一旦改字段名，测试会失败，而不是让友商表格静默变空。fixture 中的数值均为虚构。

## 环境与测试

- Python 3.10+、`requests`；Linux 环境开发验证。
- `python3 -m unittest discover -s tests -v`——26 个离线用例（汇率、财年映射、F10/MSN 抽取、标准化、监测）全绿。

## 持续集成

`ci/` 里备有 GitHub Actions 工具包：把 `ci/ci.yml` 复制到 `.github/workflows/ci.yml` 即可启用。运行范围为 drift 契约测试与 fx、auto-financials、company-detail、normalize 四个套件；monitor 套件暂不纳入——其中两个用例依赖不在仓库里的运营侧配置（见 `ci/README.md`）。

## 版本

v1.0.0 —— 见 [CHANGELOG.md](CHANGELOG.md)（含剥离时的适配说明）。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
