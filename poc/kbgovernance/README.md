# 企业知识库质量治理 PoC

自造中文语料上的三模块缺陷检测原型：**知识缺口**（语义聚类 + 段落级检索覆盖度）、
**内容腐化**（4 条规则加权打分）、**重复冗余**（文档两两余弦 + 连通分量）。
以及在此之上做的两个算法实验：检索粒度 × 打分方案对照、阈值可迁移性评测。

本目录是论文里**所有数字的唯一合法来源**。文档、答辩 PPT、论文正文里出现的每一个
指标值，都必须能在本目录的产物文件里原样找到。

---

## 一、一键复现

```bash
cd D:/26code/毕设/poc/kbgovernance
"C:/Program Files/Git/bin/bash.exe" run_all.sh
```

**`HF_HOME` 必须指向 `D:/hf_cache`**，否则模型权重会落进 C 盘用户目录，长期挤占系统盘。
`run_all.sh` 已内置默认值 `HF_HOME="${HF_HOME:-D:/hf_cache}"`，可用环境变量覆盖。

四个步骤：

| 步骤 | 脚本 | 做什么 | 实测耗时 |
|---|---|---|---|
| 0/4 | 环境自检 | 校验 numpy / pandas / scikit-learn 与 HDBSCAN 可用，检查 FlagEmbedding 是否可用 | < 1 秒 |
| 1/4 | `gen_data.py` | 生成 300 篇文档 + 2000 条工单 + ground truth（缺口意图 / 腐化文档 / 重复组） | ≈ 0.6–0.8 秒 |
| 2/4 | `embed.py` | 用 `BAAI/bge-small-zh-v1.5` 把文档、工单、文档段落向量化，落盘 `.npy` | ≈ 14–34 秒 |
| 3/4 | `detect.py` | 跑三模块检测 + 与 ground truth 对比评估，写出全部指标 CSV 与 `metrics.json` | ≈ 5.6–6.0 秒 |
| 4/4 | 产物核对 | 逐个检查产物文件是否存在及其字节数 | < 1 秒 |

预期总耗时约 65 秒（端到端，`run_all.sh` 起止时间戳之差）。
耗时字段本身每次运行会有抖动（向量化 14–34 秒取决于模型是否已在缓存），
**所有指标值不受影响**。

模型加载有三级自动降级：FlagEmbedding → sentence-transformers → TF-IDF char 2-gram。
实际用了哪一级写在 `embeddings_meta.json` 里，`detect.py` 读该文件，
保证不会出现「降级了却声称用了 BGE」的情况。

---

## 二、脚本清单

| 脚本 | 用途 | 运行方式 |
|---|---|---|
| `gen_data.py` | 生成合成语料与 ground truth。`random.seed(42)` + `np.random.seed(42)` | `python gen_data.py` |
| `embed.py` | 文档 / 工单 / 段落三级向量化，落盘 `doc_emb.npy`、`ticket_emb.npy`、`ticket_cover.npy`、`embeddings_meta.json` | `python embed.py` |
| `detect.py` | 三模块检测与评测，写出 `gap_threshold.csv` / `dup_threshold.csv` / `corrupt_docs.csv` / `dup_groups_best.csv` / `top15_gaps.csv` / `metrics.json` | `python detect.py` |
| `granularity_exp.py` | 检索粒度（整篇 / 段落）× 5 种打分方案对照，算工单级与意图级两种 AUC。段落切分与向量化直接复用 `embed.py` 的实现，并把重算的 cover 与 `ticket_cover.npy` 逐元素比对做自校验 | `python granularity_exp.py`（别名入口 `python granularity.py` 等价） |
| `corrupt_rule_ablation.py` | 内容腐化 4 条规则的 leave-one-rule-out 与 only-Rn 消融。权重与判定阈值一律从 `metrics.json:corrupt` 读，不在本文件里硬编码第二份 | `python corrupt_rule_ablation.py` |
| `check_numbers.py` | 数字纪律门禁：扫三份文档里的每个数值断言，判定它能否在本目录产物里找到出处 | `python check_numbers.py` |

`granularity_exp.py` 与 `corrupt_rule_ablation.py` 不在 `run_all.sh` 的四步里，
需要时单独跑；两者都是纯 CPU、无随机性的确定性脚本。

---

## 三、产物清单

### 机读指标产物（论文数字的唯一合法来源）

| 文件 | 承载哪类指标 |
|---|---|
| `metrics.json` | 三模块主结果：embedding 规模与模型、gap 的 P/R/F1 与簇明细、corrupt 的 P/R/F1 与规则命中、dup 的 P/R/F1 与重复组明细、总耗时 |
| `granularity.csv` | 检索粒度 × 打分方案：10 行（2 粒度 × 5 方案），列 `auc`（工单级）/ `auc_intent_median`（意图级）/ `n_tickets` / `n_labeled` |
| `granularity_dup.csv` | 两种粒度下真实重复组的组内两两最大余弦：`n_groups` / `mean_max_sim` / `min_max_sim` / `max_max_sim` |
| `corrupt_rule_ablation.csv` | 内容腐化规则消融：9 行设置，`all` 行必须与 `metrics.json:corrupt` 的 P/R/F1 逐位一致 |
| `gap_threshold.csv` | 知识缺口扫参：min_cluster_size × threshold 的簇数、检出意图数、P/R/F1 |
| `dup_threshold.csv` | 重复冗余扫参：threshold 的组级与文档级 P/R/F1、检出组数与篇数 |
| `dup_groups_best.csv` | 逐重复组明细：`size` / `max_sim` / `is_true_group`（组内余弦区间的原始出处） |
| `corrupt_docs.csv` | 逐篇腐化文档明细：`last_modified` / `risk_score` / `rule_hits` / `reasons` |
| `top15_gaps.csv` | 疑似缺口 Top15：`intent` / `size` / `cover_median` / `rep_ticket` / `is_true_gap` |
| `ground_truth.json` | ground truth：缺口意图列表、腐化文档 ID 列表、重复组、`gap_ticket_count` / `gap_ticket_ratio` / `seed` / `base_date` |
| `embeddings_meta.json` | 实际使用的 embedding 方案与模型、维度、`encode_seconds`、各语料条数、模型下载体积 |
| `derived_metrics.csv` | **派生指标长表**（`derived_key,value,formula,inputs,source_files`，50 行）：跨场景极差、跨语料/跨模型差值、F1 均值与标准差、消融下降幅度、覆盖度与吞吐等。每个值都由上表里的实测产物按 `formula` 算出，`inputs` 列给出被代入的原始键值，`source_files` 列给出上游产物。论文里的**每一个派生数字都必须在此表有对应行**；`formula` / `inputs` 两列只是公式文本，**不是**可引用的数值出处，门禁只读 `value` 列 |

### 备查产物（已完成实测、不进论文正文，**不得删除**）

`standardize/` 整目录是这一层。它对应技术方案 §6.3 的 **E7–E14 共 8 条实验**：实验本身全部跑完、数据全部落盘，
但它们服务的「阈值可迁移性评测」立论已被实测证伪（见技术方案 §5.3 与 §1.5），题目定稿后不再承诺该方向，
因此**这些数字不写进论文正文**。

| 产物 | 对应实验 | 用途 |
|---|---|---|
| `standardize/mechanism.csv` | E8 单调等价性 | 8 种打分与 cover 的 Spearman ρ：ABS/S1/S2 精确 −1.0（严格单调，AUC 恒等 0.968）；S6 −0.999817 但非严格单调故 AUC 可变 |
| `standardize/results_auc.csv` | E9 5 场景 AUC 扫描 | 8 方案 × 5 场景（α/β/γ/γ-X/δ）的 AUC、best F1、召回全部门槛阈值 |
| `standardize/results_transfer.csv` | E7 / E10 阈值迁移 | α 标定阈值原样搬到 β/γ/γ-X/δ 的 P/R/F1 与 AUC 衰减 |
| `standardize/results_banking77_{en,zh}.csv` | E11 双模型 × 双语种 | banking77 全量 + KB减半 + KB仅20意图，ABS AUC 0.9538（en）/ 0.7925（zh），S3 崩到 0.4344 / 0.4946 |
| `standardize/results_xfer_banking77{,_en,_zh}.csv` | E7 / E11 跨语料迁移 | 中文语料标定的 `cover ≤ 0.6463` 搬到 banking77，77/77 全判为缺口，F1 0.8148→0.3261 |
| `standardize/ablation.csv` | E12 分组标准化消融 | 14 个标准化变体 × α，外加 6 个关键变体 × 5 场景（**多段表结构**，见 `产物索引.md`） |
| `standardize/results_directions.csv` | E13 度量陷阱 | 方向 A/B 变体 × 4 场景：A2 阈值极差仅 0.0018 但 AUC 只有 0.1120 |
| `standardize/results_directionC.csv` | E14 固定检出比例 | 10%–30% 检出比例 × 4 场景推出的阈值与 P/R/F1 |
| `standardize/scenario_meta.json`、`standardize/banking77_meta{,_en,_zh}.json` | E9 / E11 配套 | **§5.3.3 边界表的唯一数据源**：5 场景与 banking77 双模型的 cover min/mean/max/sd |

**为什么必须保留**：论文不写这些实验，但答辩时评委完全可能追问「你为什么不用 AUC 1.0000 的 S4 min 聚合 / S3 域内标准化」。
那时需要当场翻开 CSV 回答「它在 banking77 真实语料上只有 0.8849，S3 更只有 0.4344 / 0.4946，比随机还差」——
这句话的说服力来自可复核的原始数据，而不是答辩话术。删掉这些文件，这条立论就再无任何落盘证据，
「已完成实测」这句话也随之变成无法兑现的承诺。

其中有三组数字虽然文件归在这一层，**但已被正文引用**（经 `derived_metrics.csv` 转出）：
跨场景极差 0.0264、单调等价 ρ=−1.0、跨语料迁移 F1 0.3261、方向 A2 极差 0.0018 / AUC 0.1120、
方向 C 固定 25% 的 σ=0.0873 与均值 0.5522。

**逐文件清点与「E7–E14 声明 vs 实际产物」的核对结论见 [`产物索引.md`](产物索引.md)**（覆盖 `standardize/` 下全部 31 个文件，
含三对逐字节相同的历史副本、四个日志、原始语料与字节码）。

### 中间产物（不是指标来源）

`docs.csv`、`tickets.csv`、`doc_emb.npy`、`ticket_emb.npy`、`ticket_cover.npy`、
`standardize/data/banking77_{train,test}.csv`、`standardize/run_std.log`、
`standardize/directions.log`、`standardize/exp4_{en,zh}.log`、`standardize/__pycache__/`、
`run_all.log`、`run_all_repro.log`、`RESULT.md`、`figures/`（ASCII 图）。

> `standardize/STANDARDIZE_RESULT.md` 是探索期散文报告。它里面每个数字都能在同目录 CSV 里找到，
> 但**它本身不是合法出处**——门禁明确不扫它，因为「从散文反推」正是本项目已确认的数字失真来源。

### 门禁自身的产物

`check_numbers_report.md` —— `check_numbers.py` 每次运行重新生成的核查报告。

---

## 四、数字纪律

**论文与答辩里的任何数字，都必须能在 `metrics.json` / `granularity.csv` /
`granularity_dup.csv` / `corrupt_rule_ablation.csv` / `standardize/*.csv` / `standardize/*.json` /
`derived_metrics.csv` 中找到。** 其中派生数字（均值、标准差、极差、差值、消融幅度）
统一登记到 `derived_metrics.csv`，并在 `formula` / `inputs` / `source_files` 三列
留下「从哪些实测值按什么公式算出来」的自证链；门禁只把该表的 `value` 列当出处。

改完文档自查：

```bash
cd D:/26code/毕设/poc/kbgovernance
python check_numbers.py
```

- 退出码 **0**：所有文档都没有指标类数字缺出处。
- 退出码 **1**：任一文档存在指标类数字找不到产物出处。终端逐文档分块列出
  行号、数字与上下文，报告 `check_numbers_report.md` 的 `0. 总览` 是三份文档的
  合计表，各文档自己的 `n.1` 小节是同一批内容的表格版。
- 退出码 **2**：待检查的文档路径不存在。

用法：`python check_numbers.py`（默认扫上级目录三份文档：`企业知识库质量治理系统技术方案.md`、
`本科版实施方案.md`、`数字溯源审计.md`）、`python check_numbers.py a.md b.md`
（位置参数可传 0 到多个，不传即默认三份）、`python check_numbers.py --report out.md`、
`python check_numbers.py --selftest`（只跑判定逻辑自证，不读产物也不写文件）。

判定分七类，只有最后一类里「疑似指标」的那部分会影响退出码：

| 状态 | 含义 | 影响退出码 |
|---|---|---|
| `ALLOWED` | 命中脚本里 `ALLOWED_UNSOURCED` 登记的例外（默认空表） | 否 |
| `STRUCTURAL` | 章节号（含 `§2.1` 引用与表格「文档位置」列）/ 外部文件行号（`RESULT.md` 418 行）/ 年份日期 / 列表序号 / SQL 字段长度 / 模型维度参数量 / 版本号 / 端口号 / 随机种子 —— 明显不是指标的编号，按正则自动识别 | 否 |
| `OK` | 产物中有同值（容差 1e-6）；数字后紧跟 `%` 时额外做一次百分数↔小数换算 | 否 |
| `ROUNDED` | 产物值按该数字的小数位四舍五入后相等 | 否，但需人工确认语义一致 |
| `EXTERNAL` | 参考文献著录 / arXiv 编号 / 模型规格 / 依赖安装说明等引用他人或外部标准的数字 | 否 |
| `CITED` | 引用语境：数字落在 markdown 表格的引用列（表头为「文档写的数字」/「断言」/「出处」/「判定」/「偏差性质」/「未被引用的内容」等），或落在带溯源判定词（`受审集合内无` / `仅见于` / `已被实测修正` / `改判` …）的行里 —— 即该文档在**转述并判定**他处数值（日志值、被审文档原值、审计自身计数），而非自己做了一次实测断言。判据是**位置与措辞**，不是数值白名单 | 否 |
| `UNSOURCED` | 找不到任何出处 | **仅其中的「指标类」致命** |

`CITED` 的存在是因为 `数字溯源审计.md` 整篇都是对 `企业知识库质量治理系统技术方案.md`
数值的逐条溯源判定：它表格里「文档写的数字」列装的是**被审文档**写的值，
「出处（旁注）」列装的是**日志或 RESULT.md** 里读到的值，两者本就不该在
`poc/kbgovernance/` 的产物集合里找。`CITED` 按表头与判定词识别，不针对任何
具体数值开豁免；`--selftest` 里有反向自证——普通正文里的裸指标数字（`AUC 0.9137`）
仍必须判 `UNSOURCED`。

「指标类」= 小数位 ≥ 3，或数字左右各 20 字内出现
F1 / AUC / precision / recall / ROC / 阈值 / 秒 / ms / MB / 耗时 / 相似度 /
准确率 / 召回 / 精确率 / 标准差 / 极差 / 覆盖度 / 检出 等指标词。

`ROUNDED` 一节在报告里同时给出**文档上下文**与**产物值**：同值不同义的情况
（例如文档说的是组内余弦相似度，产物那一格却是 AUC）只能靠这一对信息人工看出来，
脚本不做语义推断，也不靠放宽容差把问题掩盖掉。

`ALLOWED_UNSOURCED` 常量在脚本头部，**默认为空** —— 真实差异必须先暴露出来，
人工逐条确认后才登记进来。

---

## 五、环境坑

**`which bash` 命中的是 WSL，不是 Git Bash。** 本机解析顺序为
`C:\Windows\System32\bash.exe`（WSL，最先命中）→ WindowsApps →
`C:\Program Files\Git\bin\bash.exe`。直接敲 `bash run_all.sh` 会进 WSL，
里面没有 WindowsApps 的 python 垫片，直接报 `python: command not found`。

必须显式用完整路径调用 Git Bash：

```bash
"C:/Program Files/Git/bin/bash.exe" run_all.sh
```

注意是 Windows 路径 `C:/Program Files/...`，不能写 Git Bash 风格的 `/c/Program Files/...`。

其它本机约束：

- `HF_HOME=D:/hf_cache`，否则权重落 C 盘。
- torch 必须装 CPU 版：`pip install torch --index-url https://download.pytorch.org/whl/cpu`，
  否则会拉到约 2.5GB 的 CUDA 完整版。
- `python -m venv` 隔离环境：装某些包（如 ortools）会降级全局 protobuf，污染共享 site-packages。

---

## 六、复现性实测

已实测：连续跑第二遍后，`gap_threshold.csv` / `dup_threshold.csv` /
`ground_truth.json` / `top15_gaps.csv` 与首跑**逐字节相同**；
`metrics.json` 仅耗时字段抖动（`encode_seconds`、`seconds`、`total_seconds`），
**所有指标值完全一致**。
