#!/usr/bin/env bash
# 一键重建本项目的第三方参考仓库克隆体。
#
# 用法:
#   bash reference/clone_references.sh              # 全部类别
#   bash reference/clone_references.sh algo         # 只克隆算法参考
#   bash reference/clone_references.sh product      # 只克隆产品形态对标
#   bash reference/clone_references.sh stack        # 只克隆技术栈骨架
#   bash reference/clone_references.sh annotate     # 只克隆标注工具
#
# 克隆体落在 reference/repo/，已由 .gitignore 排除，不进入本仓库历史。
# 每个仓库固定到下列 commit SHA，保证参考对象稳定可复现。
# 清单与筛选理由见 reference/REFERENCES.md。
set -euo pipefail

REF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${REF_ROOT}/repo"
mkdir -p "$DEST"

CATS=("$@")
if [ ${#CATS[@]} -eq 0 ]; then CATS=(algo product stack annotate); fi

# 目录名|owner/repo|category|commit-sha|mode
REPOS+=("hdbscan|scikit-learn-contrib/hdbscan|algo|bb01526bf18c92e35ca0b4f5307c6d4248ddf5dc|full")
REPOS+=("mteb|embeddings-benchmark/mteb|algo|57bd86c84afdc54e822851426ab3bea764757573|full")
REPOS+=("text-dedup|ChenghaoMou/text-dedup|algo|7538f3ec6a28e72a86de5978e58655175b46a11e|full")
REPOS+=("galactic|taylorai/galactic|algo|f7af3398f3846429335547479238910925c040d2|full")
REPOS+=("simhash-py|seomoz/simhash-py|algo|cb966253b5ad7a056b3bc9a5d24a4c9ca8153fb8|full")
REPOS+=("beir|beir-cellar/beir|algo|ef83d29307061c65d04b035b4f4e7c18bd8374af|full")
REPOS+=("datasketch|ekzhu/datasketch|algo|c7eaaeea3f39909f906a9cf8ad4d21a878cb4e07|full")
REPOS+=("OpenMetadata|open-metadata/OpenMetadata|product|b2f163868e629ae2a659f6d59837b0d21481d189|full")
REPOS+=("sourcebot|sourcebot-dev/sourcebot|product|a5fcd2703e605c08d49ebda9b965997eaf00c21b|full")
REPOS+=("repowise|repowise-dev/repowise|product|bf7f05444fc4ce58d652c6ddae2ea6c7ea011ad2|full")
REPOS+=("docmost|docmost/docmost|product|744c82bdf86f454ca44a2e19dc150900e884a11e|full")
REPOS+=("outline|outline/outline|product|2f68f32b40c456a7a290a76261f3e0a60b6204ba|full")
REPOS+=("wiki|requarks/wiki|product|41efedfe1abc88585e888c3daf936dd7723e20c4|full")
REPOS+=("full-stack-fastapi-template|fastapi/full-stack-fastapi-template|stack|b1125d8839482cb7bbae603ddc6d0081bf87532e|full")
REPOS+=("sqlmodel|fastapi/sqlmodel|stack|462b59d9cd1cc3d9072735435330ef9ab6d15cbf|full")
REPOS+=("label-studio|HumanSignal/label-studio|annotate|5d3ae6fa6235e76bbb64d48c28a89e6ef2b895f0|treeless")
REPOS+=("argilla|argilla-io/argilla|annotate|5338519accb13ae422f8bf9c0642651c249c49af|full")

for entry in "${REPOS[@]}"; do
  IFS="|" read -r dir slug cat sha mode <<< "$entry"
  want="no"
  for c in "${CATS[@]}"; do [ "$c" = "$cat" ] && want="yes"; done
  [ "$want" = "yes" ] || continue

  target="${DEST}/${dir}"
  if [ -d "${target}/.git" ]; then
    echo "skip  ${slug}（已存在）"
    continue
  fi

  echo "clone ${slug} [${mode}] ..."
  if [ "$mode" = "treeless" ]; then
    # 只取 commit + tree，blob 按需拉取：避免体积极大的仓库在 clone 阶段卡死
    git clone --quiet --filter=blob:none --depth 1 --single-branch --no-checkout \
      "https://github.com/${slug}.git" "$target"
    git -C "$target" fetch --quiet --depth 1 origin "$sha"
  else
    git clone --quiet --depth 1 --single-branch "https://github.com/${slug}.git" "$target"
    git -C "$target" fetch --quiet --depth 1 origin "$sha"
    git -C "$target" checkout --quiet FETCH_HEAD
  fi
  echo "  -> ${sha:0:8}"
done

echo "完成。克隆体位于 ${DEST}"
