# AGENTS.md

本仓库是 2027 届本科毕业设计项目：**《基于语义聚类与时效性分析的企业知识库质量治理系统设计与实现》**。

当前状态：选题已定稿，算法原型（PoC）已完成全链路实测，系统实现按 17 周排期推进中（2026-10-14 → 2027-02-09，W10 末系统冻结）。

---

## 先读这些

| 想知道 | 读 |
|---|---|
| 题目为什么定这个 | [`docs/选题调研/最终裁决与选型决策.md`](./docs/选题调研/最终裁决与选型决策.md) |
| 接下来做什么、到哪天 | [`docs/技术方案/本科版实施方案.md`](./docs/技术方案/本科版实施方案.md) |
| 系统怎么设计 | [`docs/技术方案/企业知识库质量治理系统技术方案.md`](./docs/技术方案/企业知识库质量治理系统技术方案.md) |
| 术语怎么说 | [`GLOSSARY.md`](./GLOSSARY.md) |
| 已做过的架构决策 | [`docs/adr/`](./docs/adr/) |
| 原型怎么跑 | [`poc/kbgovernance/README.md`](./poc/kbgovernance/README.md) |

---

## 分支管理

### 模型

采用 **GitHub Flow 精简版**。只有一条长期分支：

```
main ──┬── feature/<slug> ──→ PR ──→ main（合并后删除分支）
       │
       ├── fix/<slug>     ──→ PR ──→ main（合并后删除分支）
       │
       └── tag: v0.x.0（里程碑，标在满足关卡的合并提交上）
```

| 分支 | 寿命 | 从哪切 | 合到哪 | 何时删 |
|---|---|---|---|---|
| `main` | 长期 | — | — | 永不 |
| `feature/<slug>` | 天级 | `main` | `main`（走 PR） | 合并后立即删 |
| `fix/<slug>` | 天级 | `main` | `main`（走 PR） | 合并后立即删 |

**为什么不设 `develop` / `release` / `hotfix` 分支**：决策依据见 [ADR-0001](./docs/adr/0001-branch-model-github-flow.md)。一句话：单人项目维护两条长期分支，集成收益为零、发散成本实打实；没有对外发版需求就不需要 `release/*`；没有生产环境就不需要 `hotfix/*`。

### 命名规范

```
feature/<slug>          例：feature/corpus-reproducibility
fix/<slug>              例：fix/gap-threshold-precision
```

- `<slug>` 用小写 kebab-case，英文，见名知意，不含日期、不含「我的」「临时」这类词。
- 有对应 GitHub Issue 时用 `feature/<issue号>-<slug>`，例：`feature/42-corpus-reproducibility`，保证分支与工单可互相追溯。
- 分支名里不写「阶段」「第 X 轮」——一个分支做一件事，做完就合。

### 生命周期

1. **切分支**：`git switch -c feature/<slug> main`——永远从 `main` 切，不从别的 feature 切。
2. **干活**：在分支上提交，频繁推送 `git push -u origin <branch>`。
3. **开 PR**：`gh pr create --fill`，正文写清「改了什么 / 为什么 / 怎么验证」。有 issue 就 `Closes #<n>`。
4. **自查**：本地跑通复现命令（见下），确认无回归，再请自己 review 一遍 diff。
5. **合并**：`gh pr merge --squash`（单人项目保持线性历史，main 上一个提交对应一个变更单元）。
6. **删分支**：`git push origin --delete <branch>`，本地 `git branch -d <branch>`。
7. **回到 main**：`git switch main && git pull --ff-only`。

**一个分支只做一件事。** 发现第二个任务就另开分支，不要在一个分支里混着做。

### 提交规范

用 [Conventional Commits](https://www.conventionalcommits.org/)：`<type>(<scope>): <主题>`。type 用英文小写，主题用中文。

| type | 用于 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `docs` | 文档变更（含本文件、ADR、术语表） |
| `refactor` | 不改变行为的重构 |
| `test` | 测试与测试脚本 |
| `perf` | 性能优化 |
| `chore` | 依赖、配置、构建杂务 |
| `ci` | 流水线配置 |

示例：

```
feat(gap): 段落级覆盖度接入缺口判定主流程
fix(embed): 修正 passages 切分时空行导致的空向量
docs(adr): 记录分支模型采用 GitHub Flow 精简版的决策
chore(deps): 固定 scikit-learn 版本到 1.5.2
```

**提交纪律**：

- 一个提交只做一件事，标题行 ≤ 50 字，主题句末尾不加句号。
- 正文写「为什么」，不写「做了什么」——做了什么看 diff 就知道。
- 不提交 `__pycache__`、`.pyc`、虚拟环境、密钥（`.gitignore` 已覆盖）。
- **不提交没有对应产物的数字变更**。改了阈值或规则权重，`metrics.json` 与对应 CSV 必须同一次提交一起更新（见下节）。

### Pull Request 流程

`main` 受分支保护规则约束，**禁止直接 push**，必须走 PR。单人项目的规则设定（依据见 ADR-0001）：

| 规则 | 状态 | 说明 |
|---|---|---|
| Require a pull request before merging | ✅ 开 | 每次进 `main` 都留一条可追溯的 PR 记录 |
| Require status checks to pass | ⏸ 暂关 | 当前无 CI 流水线，勾了会让所有 PR 卡死；CI 落地后启用 |
| Require review approvals | ❌ 关 | 单人项目无法批准自己的 PR，开启会导致 PR 永远无法合并 |
| Dismiss stale approvals | ❌ 关 | 同上 |
| Include administrators | ✅ 开 | 规则对自己同样生效 |
| Allow force pushes / deletions | ❌ 关 | `main` 历史不可重写 |

**自查清单**（开 PR 前逐条过）：

- [ ] 复现命令跑通了，产物文件已更新
- [ ] `poc/kbgovernance/check_numbers.py` 通过（若改动了任何指标）
- [ ] 文档里出现的每个数字，都能在 `poc/kbgovernance/` 的产物里找到出处
- [ ] 改动如果与某条 ADR 冲突，在 PR 里显式指出来，而不是默默推翻
- [ ] 没有把 `__pycache__`、临时脚本、密钥带进来

### 里程碑 tag

`main` 上的关卡用 annotated tag 记录，**不建 `release/*` 分支**：

```bash
git tag -a v0.1.0 -m "G1 题目与范围锁定" <commit>
git push origin v0.1.0
```

- 格式 `v<major>.<minor>.<patch>`，major 留给系统成型，minor 对应方案里的关卡（G1…G8），patch 对应关卡内的修订。
- tag 打在**满足关卡的合并提交**上，不要打在关卡前的中间提交上。
- tag 一经推送不改写。关卡判错就补一个 patch tag，不动历史。

---

## 数字纪律

**本项目的全部指标值，只允许来自 `poc/kbgovernance/` 下的机读产物。** 完整规则见 [ADR-0002](./docs/adr/0002-numbers-traceable-to-artifacts.md)。

- 论文、PPT、页面、文档里出现的每个数字，必须能在产物文件里按「文件路径 + 列/行」原样找到。
- **禁止从叙述性文本反推数字**——`RESULT.md`、方案文档正文、聊天记录都不是数据源。
- 找不到出处的数值写 `【无出处】`，**不允许补一个看起来合理的数**。
- 改动阈值、规则权重、打分形式，必须同一次提交里更新 `metrics.json` 与对应 CSV。
- **反向点必须与正向结论同表呈现**，不得只报其一。已知的一处：粒度消融中 `doc_level/max-min` 意图级 AUC 0.928 高于同粒度基准 `max-cosine` 的 0.8880。
- 消融与迁移类负结果同样落盘（例：`corrupt_rule_ablation.csv` 的 `drop_R3` 的 `delta_f1=0`），作为主动报告的负面发现写进论文，不省略。

---

## 文档规则

1. **只描述当前状态**：文档与代码注释写当前实现，不追加变更历史、不并列已作废的旧方案。功能从 A 改成 B，就把 A 改掉。
2. **冲突先报告**：代码、测试与文档三者不一致时，先报告冲突并列出假设，不自行选一方当真；不把尚未确认的实现偏差写成新的业务规则。
3. **临时记录任务结束即删**：任务期间的计划、笔记与过程结论写在临时记录里，结束时删除，不并入长期文档。

补充：

- 文档写在 `docs/` 下，按性质分两类目录：`docs/选题调研/`（选型决策链，从调研到最终裁决）与 `docs/技术方案/`（定稿后的方案与实施）。`docs/adr/` 与 `docs/agents/` 是工具管理目录，不要往里塞别的东西。
- 引用路径用仓库根相对路径（如 `poc/kbgovernance/metrics.json`），不要写本机绝对路径。

---

## 环境与复现

```bash
cd poc/kbgovernance
"C:/Program Files/Git/bin/bash.exe" run_all.sh
```

- `HF_HOME` 必须指向 `D:/hf_cache`（`run_all.sh` 已内置默认值），否则模型权重落进 C 盘系统盘。
- 纯 CPU，`BAAI/bge-small-zh-v1.5`（512 维，FlagEmbedding）。模型加载有三级自动降级，实际级别写在 `embeddings_meta.json`，`detect.py` 读它——**不允许出现「降级了却声称用了 BGE」**。
- 耗时字段跨机器必然波动，**指标值不受影响**。

---

## 参考仓库

`reference/repo/` 是第三方开源仓库的本地克隆体，**不入库**。入库的只有两份文件：

| 文件 | 内容 |
|---|---|
| `reference/REFERENCES.md` | 清单：每个仓库的用途、筛选理由、许可证、固定 commit SHA |
| `reference/clone_references.sh` | 按类别重建克隆体的脚本（SHA 固定，可复现） |

克隆体不入库的理由：体积大、各自携带许可证、会与上游分叉污染本仓库历史。需要参考时按类别重建：

```bash
bash reference/clone_references.sh algo        # 算法参考（三模块方法谱系 / 嵌入 / 评测协议）
bash reference/clone_references.sh product     # 产品形态对标（健康度评分 / 知识库 / 数据治理）
bash reference/clone_references.sh stack       # 技术栈骨架（W7-W8 Web 交付）
bash reference/clone_references.sh annotate    # 标注工具（W3 人工标注关卡）
bash reference/clone_references.sh             # 全部
```

**纪律**：

- 借鉴思路、**自己实现**。第三方代码不得直接拷进 `poc/` 或未来的系统实现目录。
- 引用第三方实现时，在代码注释里写明来源仓库与 commit SHA，并先确认其许可证允许本用途。
- 引入新的参考仓库时，先在 `reference/REFERENCES.md` 写清「它对应我们的哪个模块、为什么值得看」，再克隆。

---

## Agent skills

### Issue tracker

工单与规格存放在 GitHub Issues，用 `gh` CLI 读写。见 [`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md)。

### Triage labels

使用五个默认 triage 角色标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 [`docs/agents/triage-labels.md`](./docs/agents/triage-labels.md)。

### Domain docs

single-context 布局：根目录 `GLOSSARY.md` + `docs/adr/`。见 [`docs/agents/domain.md`](./docs/agents/domain.md)。
