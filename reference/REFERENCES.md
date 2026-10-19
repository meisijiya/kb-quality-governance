# 参考仓库清单

> 目的：避免重复造轮子，同时为论文的「相关工作 / 方法选型」与答辩的「商业对标 / 系统边界」提供可核查的外部参照。
>
> **克隆体不入库。** `reference/repo/` 已被 `.gitignore` 排除；入库的只有本清单与 `clone_references.sh`。
> 需要时按类别重建：`bash reference/clone_references.sh <algo|product|stack|annotate>`（不带参数取全部）。
>
> 每个仓库固定到下表列出的 commit SHA，保证参考对象稳定可复现。

**纪律**：借鉴思路、自己实现；第三方代码不得直接拷进 `poc/` 或系统实现目录。引用其实现时在代码注释里写明来源仓库与 SHA，并先确认许可证允许本用途。

> **关于表中的数字**：star 数、许可证、commit SHA、仓库体积是**第三方仓库的元数据**，不是本课题的指标值，因此不受 `AGENTS.md` 数字纪律（指标值只许来自 `poc/kbgovernance/` 产物）的约束。它们同样遵循「可溯源」原则——分别取自 GitHub API 与本地 git 元数据，未手抄。

---

## 筛选口径

只用三条标准，且三条都要满足才进清单：

1. **对得上我们的某个具体模块或关卡** —— 不是「相关领域里很流行」，而是「正好回答我们某个待论证的问题」。
2. **能落到具体文件看** —— 有可读的实现或文档，不是只有一句话简介的壳。
3. **许可证允许借鉴** —— AGPL 类仓库只作产品形态与设计思路参考，不抄代码。

> 调研过程用了 GitHub Explore 的 `find_repos` / `explore` / `find_similar`。一个实测结论：**抽象主题（知识库治理、文档健康度、新鲜度检测）的关键词搜索信噪比极低**——top 结果几乎全是高星通用巨仓（`ossu/computer-science`、`agency-agents` 这类），与主题无关。可信路径是：以已知锚点走 `find_similar`，或直接按 owner/repo 调 API 取真实元数据。清单里每条 SHA 与许可证都取自 git 元数据与 GitHub API，未经手抄。

## 一、算法参考 —— 三模块的方法谱系、嵌入选型、评测协议

这一组直接决定论文的方法章节怎么写：每个仓库对应一个「我们为什么这么做 / 为什么不那么做」的论证点。

| 仓库 | Star | 许可证 | 用途 | 固定 SHA |
|---|---:|---|---|---|
| [`scikit-learn-contrib/hdbscan`](https://github.com/scikit-learn-contrib/hdbscan) | 3156 | BSD-3-Clause | 知识缺口模块 | `bb01526b` |
| [`embeddings-benchmark/mteb`](https://github.com/embeddings-benchmark/mteb) | 3466 | Apache-2.0 | 嵌入层选型 | `57bd86c8` |
| [`ChenghaoMou/text-dedup`](https://github.com/ChenghaoMou/text-dedup) | 764 | Apache-2.0 | 重复冗余模块 | `7538f3ec` |
| [`taylorai/galactic`](https://github.com/taylorai/galactic) | 327 | Apache-2.0 | 重复冗余模块 / 数据管线 | `f7af3398` |
| [`seomoz/simhash-py`](https://github.com/seomoz/simhash-py) | 423 | MIT | 重复冗余模块 | `cb966253` |
| [`beir-cellar/beir`](https://github.com/beir-cellar/beir) | 2312 | Apache-2.0 | 评测协议 | `ef83d293` |
| [`ekzhu/datasketch`](https://github.com/ekzhu/datasketch) | 2971 | MIT | 重复冗余模块 | `c7eaaeea` |

### `scikit-learn-contrib/hdbscan`

**知识缺口模块**

HDBSCAN 官方实现。看 min_cluster_size 的真实语义与噪声点处理，支撑我们 min_cluster_size=5 / 10 两种配置下 F1 完全相同这一实测结论的解释。

· 许可证 `BSD-3-Clause`；3156 star；最近提交 2026-10-08；上游简介：A high performance implementation of HDBSCAN clustering.

### `embeddings-benchmark/mteb`

**嵌入层选型**

嵌入模型横评框架。已核实：中文检索子集在 `mteb/tasks/retrieval/zho/` 下，即 **C-MTEB**（`cmteb_retrieval.py`）——这正是 `BAAI/bge-small-zh-v1.5` 自己的模型卡引用的中文基准，另有 `multilingual/` 子集（含 `chinaopen_retrieval.py`）。用途：回答「为什么用 bge-small-zh-v1.5 而不是更大的模型」，并把我们的嵌入选择锚到公开横评上。

· 许可证 `Apache-2.0`；3466 star；最近提交 2026-10-19；上游简介：MTEB: State-of-the-art evaluation of embeddings across langu

### `ChenghaoMou/text-dedup`

**重复冗余模块**

一站式去重工具，把 MinHash-LSH 近重复、64/128 位 SimHash、Bloom Filter 精确去重、后缀数组子串精确去重四类策略并列在同一套接口下（已在仓库内核实）。**它不含嵌入语义去重**——这恰好标出本项目的位置：我们的「文档两两余弦 + 连通分量」走语义路线，而这条路线在该工具里是空缺的，可作论文方法选型的一处直接对照。

· 许可证 `Apache-2.0`；764 star；最近提交 2026-03-09；上游简介：All-in-one text de-duplication

### `taylorai/galactic`

**重复冗余模块 / 数据管线**

非结构化文本的端到端清洗与近重复管线，内含 `minhash_lsh.py` 实现。参考其「先清洗后去重」的流水线组织方式。

· 许可证 `Apache-2.0`；327 star；最近提交 2024-08-06；上游简介：data cleaning and curation for unstructured text

### `seomoz/simhash-py`

**重复冗余模块**

Simhash 近重复检测的极简实现。规则化视角的对照方法：与我们的嵌入余弦相比，Simhash 不依赖模型、可解释性强但召回低，适合作为论文「为何不用 Simhash」一节的论据。

· 许可证 `MIT`；423 star；最近提交 2023-05-15；上游简介：Simhash and near-duplicate detection

### `beir-cellar/beir`

**评测协议**

异构信息检索基准。用于讲清本课题「覆盖度」与检索领域「recall」的评测口径差异，守住与 RAG 的边界（见技术方案 §1.3）。

· 许可证 `Apache-2.0`；2312 star；最近提交 2025-10-16；上游简介：A Heterogeneous Benchmark for Information Retrieval. Easy to

### `ekzhu/datasketch`

**重复冗余模块**

MinHash + LSH 的经典实现。用来在论文里给我们的「文档两两余弦 + 连通分量」定方法边界：300 篇文档时 O(n²) 完全可行，MinHash-LSH 的优势要到百万级才体现，写清这个取舍是方法章节的关键论证。

· 许可证 `MIT`；2971 star；最近提交 2026-10-10；上游简介：MinHash, LSH, LSH Forest, Weighted MinHash, HyperLogLog, Hyp

## 二、产品形态对标 —— 健康度评分、知识库系统、数据治理

这一组决定答辩时怎么讲「商业对标」和「系统边界」。

| 仓库 | Star | 许可证 | 用途 | 固定 SHA |
|---|---:|---|---|---|
| [`open-metadata/OpenMetadata`](https://github.com/open-metadata/OpenMetadata) | 15513 | Apache-2.0 | 质量维度体系 | `b2f16386` |
| [`sourcebot-dev/sourcebot`](https://github.com/sourcebot-dev/sourcebot) | 3996 | MIT | 自托管治理型产品 | `a5fcd270` |
| [`repowise-dev/repowise`](https://github.com/repowise-dev/repowise) | 7852 | AGPL-3.0（强 copyleft） | 健康度评分产品形态 | `bf7f0544` |
| [`docmost/docmost`](https://github.com/docmost/docmost) | 22033 | AGPL-3.0（强 copyleft） | 知识库系统 | `744c82bd` |
| [`outline/outline`](https://github.com/outline/outline) | 40971 | GitHub 未识别出标准 SPDX 许可证（需自行核对仓库 LICENSE 文件） | 知识库系统 | `2f68f32b` |
| [`requarks/wiki`](https://github.com/requarks/wiki) | 29054 | AGPL-3.0（强 copyleft） | 知识库系统 | `41efedfe` |

### `open-metadata/OpenMetadata`

**质量维度体系**

数据治理平台，**freshness（新鲜度）是它的标准质量维度**。这是「内容腐化 / 时效性」模块在工业界的对应物，可作为论文时效性定位的外部佐证。

· 许可证 `Apache-2.0`；15513 star；最近提交 2026-10-19；上游简介：The Open Context Layer for Data and AI ,  OpenMetadata is th

### `sourcebot-dev/sourcebot`

**自托管治理型产品**

自托管的代码与文档智能工具。参考其「扫描 → 清单 → 修复」的产品流程编排，对应我们 Web 交付的三个功能面。

· 许可证 `MIT`；3996 star；最近提交 2026-10-16；上游简介：Sourcebot is a self-hosted tool that helps humans and agents

### `repowise-dev/repowise`

**健康度评分产品形态**

代码健康度评分产品，是目前最贴近「知识库健康度评分」的开源实现。答辩商业对标（AptEdge / Ravenna）的开源近邻，参考其评分维度组织与看板形态。

· 许可证 `AGPL-3.0`；7852 star；最近提交 2026-10-19；上游简介：Codebase intelligence for AI and humans: code health scores,

### `docmost/docmost`

**知识库系统**

协作知识库系统。用来定位我们的轻量看板相对完整知识库的取舍：我们不做编辑与协作，只做治理扫描与清单交付。

· 许可证 `AGPL-3.0`；22033 star；最近提交 2026-10-18；上游简介：Docmost is an open-source collaborative wiki and documentati

### `outline/outline`

**知识库系统**

团队知识库系统。作为产品形态的第二参照点，与 docmost 一起界定我们的系统边界。

· 许可证 `NOASSERTION`；40971 star；最近提交 2026-10-19；上游简介：The fastest knowledge base for growing teams. Beautiful, rea

### `requarks/wiki`

**知识库系统**

Wiki.js。经典 wiki 形态，参考其分类/标签组织对治理清单分类维度的启发。

· 许可证 `AGPL-3.0`；29054 star；最近提交 2026-10-19；上游简介：Wiki.js | Next Generation Open Source Wiki

## 三、技术栈骨架 —— W7–W8 的 Web 交付

这一组是本科版 Web 交付（FastAPI + SQLite + 轻量看板）的现成骨架，不自己造。

| 仓库 | Star | 许可证 | 用途 | 固定 SHA |
|---|---:|---|---|---|
| [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) | 46040 | MIT | Web 交付骨架 | `b1125d88` |
| [`fastapi/sqlmodel`](https://github.com/fastapi/sqlmodel) | 18423 | MIT | 数据层 | `462b59d9` |

### `fastapi/full-stack-fastapi-template`

**Web 交付骨架**

FastAPI + SQLModel + SQLite + 前端的完整模板，一条命令起服务。直接对应本科版 W7-W8 的 Web 交付形态（上传 → 扫描 → 三类清单 → 下载 CSV）。

· 许可证 `MIT`；46040 star；最近提交 2026-10-15；上游简介：Full-stack web application template with FastAPI, React, SQL

### `fastapi/sqlmodel`

**数据层**

FastAPI 官方推荐的 SQL 层，SQLAlchemy + Pydantic 合二为一。我们用 SQLite 存三类清单，参考其模型定义与迁移写法。

· 许可证 `MIT`；18423 star；最近提交 2026-10-15；上游简介：SQL databases in Python, designed for simplicity, compatibil

## 四、标注工具 —— W3 人工标注关卡

这一组对应 W3 关卡：300 条人工标注 + ≥100 条双人独立标注 + Cohen's Kappa。

| 仓库 | Star | 许可证 | 用途 | 固定 SHA |
|---|---:|---|---|---|
| [`HumanSignal/label-studio`](https://github.com/HumanSignal/label-studio) | 28492 | Apache-2.0 | W3 人工标注 | `5d3ae6fa` |
| [`argilla-io/argilla`](https://github.com/argilla-io/argilla) | 5160 | Apache-2.0 | W3 人工标注 | `5338519a` |

### `HumanSignal/label-studio`

**W3 人工标注**

最主流的多类型数据标注平台。W3 要做 300 条标注 + ≥100 条双人独立标注，参考其任务配置与多人分工流程。**注意：此仓库约 2.9 GB，常规浅克隆在本机会卡死在 pack 阶段**，因此用 treeless 模式克隆（只取 commit + tree，目录结构可浏览，blob 按需拉取），需要看具体文件时再 `git -C reference/repo/label-studio checkout <path>`。

· 许可证 `Apache-2.0`；28492 star；最近提交 2026-10-19；上游简介：Label Studio is a multi-type data labeling and annotation to

### `argilla-io/argilla`

**W3 人工标注**

面向 LLM 数据的文本标注协作工具，内置标注一致性（inter-annotator agreement）工作流，对应我们 Cohen's Kappa 的计算与报告口径。

· 许可证 `Apache-2.0`；5160 star；最近提交 2026-10-12；上游简介：Argilla is a collaboration tool for AI engineers and domain 

---

## 两个调研结论

**1. 我们的商业对标没有开源等价物。** 技术方案里的 AptEdge 与 Ravenna 在 GitHub 上搜不到有意义的开源项目（只有同名的无关小仓库）。这不是坏消息——它反过来印证了技术方案 §1.2 的论点：知识治理是**有商业付费意愿但开源供给缺口**的能力项，这正是本课题的立项理由。清单里的 `repowise` 是目前最接近的开源近邻（代码健康度评分），可作为「开源侧最接近做到什么程度」的参照。

**2. 抽象主题的 GitHub 搜索不可信。** 用「knowledge base quality governance」「documentation freshness detection」这类词搜出来的 top 结果几乎全是高星通用仓库，与主题无关。做这类调研时可信的路径是：以已知锚点为起点走 `find_similar`，或直接按 owner/repo 调 API 取真实元数据。

