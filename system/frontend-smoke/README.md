# 前端烟测：Vue 3 + Element Plus「能装能构建」实测

> **定位：这是烟测工程，不是正式前端项目。**
> 它只回答一个问题——技术方案 §4.4 第 405 行把「Vue3 + Element Plus」标注为「设计值，尚未实测」，这句话现在能不能改成实测结论。
> 本目录不含任何业务逻辑、不连后端、不含路由/状态管理/权限/主题定制，正式前端工程（W7）应另起目录，并沿用本 README 第 2 节锁定的版本与第 5 节的命令。

---

## 1. 实测结论

### 1.1 能不能装 —— 能

环境事实（`node -v` / `npm -v` / `pnpm -v` / `npm config get registry` / `npm ping`）：

```
$ node -v
v24.4.0
$ npm -v
11.6.0
$ npm config get registry
https://registry.npmmirror.com
$ pnpm -v
10.20.0
$ npm ping
npm notice PING https://registry.npmmirror.com/
npm notice PONG 148ms
npm notice PONG {
npm notice PONG   "pong": true,
npm notice PONG   "use": 0.34064599871635437
npm notice PONG }
```

安装（工作目录 `system/frontend-smoke/`，依赖精确锁版本，不带 `-g`）：

```
$ npm install --save-exact vue element-plus
added 44 packages in 19s

7 packages are looking for funding
  run `npm fund` for details
=== exit(deps)=0 ===

$ npm install --save-exact -D vite @vitejs/plugin-vue
added 37 packages in 8s

23 packages are looking for funding
  run `npm fund` for details
=== exit(devDeps)=0 ===
TOTAL_WALL_SECONDS=29
```

- 两条命令退出码均为 0，**无 WARN、无 ERR**；两段输出只有 `added N packages` 与 `looking for funding` 两类提示。
- `package-lock.json` 已生成：`lockfileVersion 3`，81 个包条目（生产 44 + 开发 37），文件 42364 字节。
- `node_modules` 落点复核（**未污染仓库其它目录**）：

```
$ ls -d node_modules
node_modules
$ ls -d ../../node_modules
ls: cannot access '../../node_modules': No such file or directory
$ ls -d ../node_modules
ls: cannot access '../node_modules': No such file or directory
$ ls -d /d/26code/毕设/node_modules
ls: cannot access '/d/26code/毕设/node_modules': No such file or directory
```

结论：**能装**。Node 24.4.0 + npm 11.6.0 下安装 Vue/Element Plus/Vite 全量成功，耗时 19s + 8s。

### 1.2 能不能构建 —— 能

```
$ npm run build
> frontend-smoke@0.1.0 build
> vite build

vite v8.3.5 building client environment for production...
transforming...
✓ 1580 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.42 kB │ gzip:   0.30 kB
dist/assets/index-Bbj9e2vT.css  360.61 kB │ gzip:  48.15 kB
dist/assets/index-BJyvwUCZ.js   982.75 kB │ gzip: 315.84 kB

✓ built in 595ms
=== exit(build)=0 ===
BUILD_WALL_SECONDS=2
```

- 退出码 0，**构建成功**，1580 个模块完成转换，构建耗时 595ms（整条命令墙钟 2s）。
- 产物目录 `system/frontend-smoke/dist/`：`index.html`（426 字节）+ `assets/` 两个文件，合计 1.3M。
- **有一条 warning（不是 error）**：

```
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rolldownOptions.output.codeSplitting to improve chunking: ...
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
```

  成因是 Element Plus 全量引入（`import ElementPlus from 'element-plus'`），单 JS chunk 982.75 kB（gzip 315.84 kB）。烟测阶段按最小工程要求**不删依赖、不降级功能**；正式工程应改为按需引入或路由级懒加载，此项留给 W7。

- `dist/index.html` 用的是**相对 base**（`./assets/...`，`vite.config.js` 里 `base: './'`），因此构建产物可被后端静态挂载到任意路径，与 P3「后端单进程静态挂载前端产物」的形态直接兼容。

### 1.3 el-table 能不能渲染出那张表 —— 能

页面用 Vite 的 `?raw` 在**构建时**直接读仓库真实产物 `poc/kbgovernance/gap_intents_best.csv`，运行时解析成表格行，**工程里没有复制任何数据**：

```js
// system/frontend-smoke/src/App.vue
import csvRaw from '../../../poc/kbgovernance/gap_intents_best.csv?raw'
```

构建产物中确认 CSV 已被内联：

```
$ grep -o "公积金提取材料,3,0.5629" dist/assets/index-BJyvwUCZ.js | head -2
公积金提取材料,3,0.5629
```

渲染校验（Playwright + Chromium，脚本 `system/frontend-smoke/render_smoke.py`，断言表头、行数、每个 intent 值，并检查页面正文不出现 `is_true_gap` / `NaN` / `undefined` / `[object Object]`）：

```
$ npm run preview -- --port 4173 --host 127.0.0.1
  ➜  Local:   http://127.0.0.1:4173/

$ python system/frontend-smoke/render_smoke.py http://127.0.0.1:4173/
[render_smoke] url = http://127.0.0.1:4173/
[render_smoke] 表头 = ['业务意图', '簇数', '意图覆盖度']
[render_smoke] 表体行数 = 5
[render_smoke] 表体单元格 = ['公积金提取材料', '3', '0.5629', '海外出差报销标准', '3', '0.5712', '密码策略例外申请', '3', '0.604', '社保转移办理', '3', '0.6083', '终端病毒处置', '3', '0.6179']
[render_smoke] 截图 = D:\26code\毕设\system\frontend-smoke\smoke.png
[render_smoke] 通过：el-table 渲染出 3 列表头 + 5 行真实数据，无控制台错误
=== exit=0 ===
```

截图：`system/frontend-smoke/smoke.png`（1200×800，28645 字节，sha256 `341c832501c221ffa15dde3535596d44dc756240cbc4edc990ae7fd7a68bc32f`），取自**生产构建产物**（`vite preview` 服务的 `dist/`）。

开发模式（`npm run dev`）同样渲染通过，作为补充证据：

```
  VITE v8.3.5  ready in 385 ms
  ➜  Local:   http://127.0.0.1:5173/
$ python system/frontend-smoke/render_smoke.py http://127.0.0.1:5173/
[render_smoke] 表头 = ['业务意图', '簇数', '意图覆盖度']
[render_smoke] 表体行数 = 5
[render_smoke] 通过：el-table 渲染出 3 列表头 + 5 行真实数据，无控制台错误
```

结论：**能渲染**。表头 3 列、行数 5 行、每行数值与 CSV 逐字一致，无控制台错误。

### 1.4 附带发现：真实产物 CSV 带 UTF-8 BOM

第一次渲染时**第一列整列为空**（表体单元格读到 `['', '3', '0.5629', ...]`）。定位结果：

```
$ head -c 16 poc/kbgovernance/gap_intents_best.csv | od -An -tx1
 ef bb bf 69 6e 74 65 6e 74 2c 6e 5f 63 6c 75 73
```

文件以 UTF-8 BOM 开头，于是首列表头实际是 `﻿intent`（`\ufeffintent`）而不是 `intent`，按列名 `indexOf` 取列返回 -1，第一列被静默取空。烟测页已做 BOM 剥离后修正：

```js
.replace(/^\uFEFF/, '')
```

**这条对 W7 有直接约束**：前端（以及任何 CSV 解析入口）必须处理 BOM，或者后端在产出时统一不带 BOM。同一批产物里 `docs.csv` / `tickets.csv` 由 `gen_data.py` 以 `encoding="utf-8-sig"` 写出（BOM 是刻意为之，Excel 打开中文不乱码），因此**「读 CSV」这件事在本项目里绕不开 BOM**。

另一处顺带核过：该 CSV 每行 ASCII 逗号数量恒为 7（8 个字段），正文里的中文顿号/逗号都是全角，**按 `,` 朴素切分是安全的**。

### 1.5 附带发现：`?raw` 会把整份 CSV（含真值列）打进前端包

`grep -c "is_true_gap" dist/assets/index-BJyvwUCZ.js` → `1`，说明 bundle 里内联的原始 CSV 文本**包含表头里的 `is_true_gap` 等评测依据列**。DOM 层没有渲染它（`render_smoke.py` 断言页面正文不含 `is_true_gap`，已通过），但包内确实带着。正式工程里前端**不应**直接读 PoC 产物 CSV，应由后端 API 只吐展示所需字段（这也是 C12「渲染行为不依赖真值列」的要求）。

### 1.6 按 lock 复现安装（`npm ci`）—— 通过，但有一个 Windows 坑

删掉 `node_modules/` 后按 lock 复现安装：

```
$ npm ci
added 81 packages in 18s

23 packages are looking for funding
  run `npm fund` for details
CI_EXIT=0  CI_WALL_SECONDS=19
```

复现后重新构建同样成功（`✓ 1580 modules transformed.` / `✓ built in 681ms` / 退出码 0），重新截图得到**字节完全一致**的 `smoke.png`（sha256 仍是 `341c832501c221ffa15dde3535596d44dc756240cbc4edc990ae7fd7a68bc32f`）。

**踩到的坑（第一次 `npm ci` 失败，原文）**：

```
npm error [Error: EPERM: operation not permitted, unlink 'D:\26code\毕设\system\frontend-smoke\node_modules\@rolldown\binding-win32-x64-msvc\rolldown-binding.win32-x64-msvc.node'] {
npm error   errno: -4048,
npm error   code: 'EPERM',
npm error   syscall: 'unlink',
npm error   path: 'D:\\26code\\毕设\\system\\frontend-smoke\\node_modules\\@rolldown\\binding-win32-x64-msvc\\rolldown-binding.win32-x64-msvc.node'
}
npm error The operation was rejected by your operating system.
npm error It's possible that the file was already in use (by a text editor or antivirus),
```

原因是**后台还挂着 `vite preview` 进程**，rolldown 的原生绑定（`.node`）被占用，Windows 不允许 unlink。杀掉 vite 进程后重跑即通过。

对 W7 的含义：**Windows 上重装前端依赖前必须先停掉 vite / node 进程**，否则 `npm ci` 会半途失败、把 `node_modules` 打成残缺状态（本次失败后 `npm run build` 直接报 `'vite' 不是内部或外部命令`）。

---

## 2. 锁定的依赖版本

以下版本从 `system/frontend-smoke/package-lock.json`（`lockfileVersion 3`）读出，与 `package.json` 中 `dependencies` / `devDependencies` 一一对应（安装时用了 `--save-exact`，包名后不带 `^`/`~`，锁文件与 package.json 写死同一版本）：

| 依赖 | 锁定版本 | 类型 | 来源 |
|---|---|---|---|
| `vue` | **3.5.44** | dependencies | `package-lock.json` → `packages["node_modules/vue"].version` |
| `element-plus` | **2.14.7** | dependencies | `packages["node_modules/element-plus"].version` |
| `vite` | **8.3.5** | devDependencies | `packages["node_modules/vite"].version` |
| `@vitejs/plugin-vue` | **6.0.10** | devDependencies | `packages["node_modules/@vitejs/plugin-vue"].version` |

关键传递依赖（同样从 lock 读出）：

| 包 | 版本 |
|---|---|
| `@vue/compiler-sfc` | 3.5.44 |
| `@vue/runtime-core` | 3.5.44 |
| `@vue/shared` | 3.5.44 |
| `rolldown`（Vite 8 的打包内核） | 1.2.15 |
| `@element-plus/icons-vue` | 2.3.2 |
| `@vueuse/core` | 15.0.0 |
| `postcss` | 8.5.31 |
| `magic-string` | 0.30.21 |
| `tinyglobby` | 0.2.17 |

lock 文件共 81 个包条目（生产 44 + 开发 37），完整清单见 `system/frontend-smoke/package-lock.json`。

**两点需要维护者知悉**：

1. `vite 8.3.5` 是当前最新主版本，内核已换成 Rolldown（build warning 里出现 `build.rolldownOptions.output.codeSplitting`），部分旧社区文章与配置写法不适用。若正式工程希望更稳，可退到 Vite 7，但本次实测没有做该对照。
2. `element-plus 2.14.7` 的按需引入（`unplugin-vue-components` + `unplugin-auto-import`）本次**未测**，烟测走的是全量引入。

---

## 3. 尚未验证

本次只做「装得上 + 构建得出 + el-table 渲染得出」三件事，以下**一律没有验证**，不得据此下结论：

- **没有真实后端联调**：没有 FastAPI、没有 `system/openapi.yaml` 契约、没有真实请求；页面数据是构建时从 CSV 读进来的静态数据。
- **没有真实建库写入 / 读回**：6 张表（`document` / `ticket` / `cluster_result` / `knowledge_gap` / `stale_document` / `duplicate_group`）一次都没建过，C12 仍然未完成。
- **没有测三类清单**：只渲染了缺口清单的 5 行意图级数据；腐化清单（文档级）、重复清单（组级）完全没碰。
- **没有测 SQLite**：技术方案 §4.4 第 406 行的「SQLite（设计值，尚未实测）」**仍然是未实测状态**，本次与 SQLite 无关。
- **没有测真实后端静态挂载**：`vite preview` 静态服务与 `vite dev` 都验过，但**没有**在真实 FastAPI 进程里静态挂载 `dist/`，也没有测 base path 挂到子目录下的表现（本次用相对 base 只是为此留了接口）。
- **没有测旧浏览器 / IE / 移动端**：只在 Chromium（Playwright 自带）桌面视口 1200×800 下截图；没测 Firefox / WebKit / Edge，也没测窄屏与暗色模式。
- **没有测 i18n**：页面全是中文硬编码，没有接 Element Plus 的 locale 包，也没做中英切换。
- **没有测 Element Plus 的其它组件**：只用了一个 `el-table`；`el-upload`（上传）、`el-statistic`（指标）、表单、树、抽屉等全部未验。
- **没有测按需引入与代码分割**：仍存在 >500 kB 的 chunk warning，未做拆包。
- **没有测深色模式与主题定制**：`element-plus/dist/index.css` 是默认浅色主题，未按方案 A 的 token 覆盖。
- **没有测依赖安装的离线可复现**：本次安装全程联网（registry 为 npmmirror，`npm ping` 148ms）。联网按 lock 的 `npm ci` 复现已通过（第 1.6 节），但**未验证**断网 / `npm ci --offline` / 换 registry 的情形。
- **没有跑任何仓库既有门禁**：本次没有触碰 `poc/kbgovernance/`，`run_all.sh` / `check_numbers.py` 均未执行；本次改动不涉及任何指标数字。
- **没有测 Windows 以外的平台**：全部在 Windows + Node 24.4.0 + npm 11.6.0 + npmmirror registry 下完成。

---

## 4. 对本项目结论的影响

### 4.1 技术方案 §4.4 第 405 行现在可以改成什么

原文：

```
| 前端 | Vue3 / React / 服务端渲染 | **Vue3 + Element Plus**（设计值，尚未实测） | 组件成熟，国内资料多 |
```

**建议措辞（由维护者统一改，本任务未改该文档）**：

```
| 前端 | Vue3 / React / 服务端渲染 | **Vue3 + Element Plus**（已实测，见 `system/frontend-smoke/`） | 组件成熟，国内资料多；已实测可安装可构建可渲染 el-table（Vue 3.5.44 / Element Plus 2.14.7 / Vite 8.3.5，Node 24.4.0 + npm 11.6.0），但尚未做后端联调与建库写入 |
```

要点：

- 只把**前端这一行**从「设计值，尚未实测」改成「已实测」，**不要**顺带把第 406 行的 SQLite 一起改——SQLite 本次完全没碰。
- 括注里保留「尚未做后端联调与建库写入」，避免「已实测」被读成「整条前端链路已验证」。
- 依据可指向 `system/frontend-smoke/README.md`（本文件）与 `system/frontend-smoke/smoke.png`。

### 4.2 对 `docs/技术方案/开发前准备清单.md` 的影响

- **C10「前端工具链烟测与依赖锁定」**：验收信号是「存在一条可重复执行的前端安装 + 构建命令，且输出可判定；依赖清单锁定版本」。本次已交付：`npm install` / `npm run build` 两条命令（第 5 节）、输出可判定（第 1 节）、版本锁定（第 2 节）。**C10 的工具链部分可以判定为通过**，但**整条 C10 是否能关闭取决于维护者对「可重复执行」的验收范围**——本次没有做离线复现、也没有在别的机器/别的 Node 版本上验证。
- **C12「六表 + Element Plus 表格渲染实测」**：**不能**因为本次截图就关闭。本次没有真实建库写入，页面读的是 PoC 的 CSV 而不是数据库；C12 要求「6 张表可写入并读回」，这一条仍然未完成。本次仅覆盖 C12 的「表格渲染」子项，且证明了一件事：**渲染用的数据源应当是后端 API，不是 PoC 产物 CSV**（见 1.5）。
- 其它引用 §4.4 的条目（如开发前准备清单的 W7 门槛表）**不应**因为本次烟测而勾选。
- 行号提醒：开发前准备清单把 §4.4 的前端/SQLite 两行记作「第 391/392 行」，技术方案当前实际是**第 405/406 行**（文件已改动，行号漂移）。改文档时按内容定位，不要按旧行号盲改。

### 4.3 给 W7 的三条具体约束

1. 前端工程起步时直接沿用第 2 节的版本组合，或显式记录一次降级/升级的实测对照。
2. 任何 CSV 读取入口都要处理 UTF-8 BOM（见 1.4）。
3. 前端只消费后端 API 吐出的展示字段，不要把真值列（`is_true_gap` / `is_true_group` / `in_control_sample` 等）带进前端包（见 1.5）。

---

## 5. 复跑步骤

在仓库根目录执行：

```bash
cd system/frontend-smoke

# 1) 安装（依赖精确锁版本；lock 文件已入库，`npm ci` 同样可用）
npm install --save-exact vue element-plus
npm install --save-exact -D vite @vitejs/plugin-vue
# 或按 lock 复现（Windows 上跑之前先停掉所有 vite / node 进程，否则可能 EPERM，见 1.6）
npm ci

# 2) 构建
npm run build

# 3) 起服务并截图（先起服务，再另开一个终端跑截图脚本）
npm run preview -- --port 4173 --host 127.0.0.1
python render_smoke.py http://127.0.0.1:4173/     # 退出码 0 即通过
```

截图脚本 `render_smoke.py` 的判定口径：表头必须是 `['业务意图', '簇数', '意图覆盖度']`，表体行数必须是 5，5 个 intent 值必须逐个出现，页面正文不得出现 `is_true_gap` / `NaN` / `undefined` / `[object Object]`，且浏览器控制台无 error；任一不满足即退出码 1。

## 6. 文件清单

```
system/frontend-smoke/
├── .gitignore          # 忽略 node_modules/ 与 dist/
├── README.md           # 本文件
├── index.html          # Vite 入口
├── package.json        # 4 个依赖，精确锁版本
├── package-lock.json   # lockfileVersion 3，81 个包条目
├── render_smoke.py     # Playwright 截图 + el-table 断言
├── smoke.png           # 渲染证据（生产构建产物，1200×800）
├── src/
│   ├── App.vue         # 页面：?raw 读 CSV → 解析 → el-table 三列
│   └── main.js         # Vue + Element Plus 全量注册
└── vite.config.js      # vue 插件 + 相对 base + fs.allow('../..')
```

`node_modules/` 与 `dist/` 已被本目录的 `.gitignore` 忽略（仓库根 `.gitignore` 已忽略 `dist/`，但不忽略 `node_modules/`，故此处补了本地忽略规则）。

**本目录是烟测工程**，产物目录 `dist/` 不入库（不入库即意味着答辩现场需要重新构建，与 P3「构建产物入库」的拍板结论不一致——正式工程应按 P3 把构建产物入库，详见 `docs/技术方案/开发前准备清单.md` 的 P3 拍板行）。
