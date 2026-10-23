/* 本文件由 data/ 下的真实产物自动生成，取值未作任何改写。
 * 数据源：top15_gaps.csv / corrupt_docs.csv / dup_groups_best.csv / metrics.json
 * 仅保留规格附录 A 允许透出的字段；评测依据列与归因列未纳入。
 */

const KB = {
  "gaps": [
    {
      "rank": 1,
      "intent": "公积金提取材料",
      "size": 18,
      "cover_median": 0.5629,
      "rep_ticket": "TK00119",
      "rep_text": "租房提取和购房提取材料一样吗，麻烦帮忙确认一下流程"
    },
    {
      "rank": 2,
      "intent": "海外出差报销标准",
      "size": 28,
      "cover_median": 0.5712,
      "rep_ticket": "TK00004",
      "rep_text": "去东南亚出差的住宿标准是多少，麻烦帮忙确认一下流程"
    },
    {
      "rank": 3,
      "intent": "海外出差报销标准",
      "size": 26,
      "cover_median": 0.5728,
      "rep_ticket": "TK01795",
      "rep_text": "海外出差津贴怎么算币种，麻烦帮忙确认一下流程"
    },
    {
      "rank": 4,
      "intent": "密码策略例外申请",
      "size": 19,
      "cover_median": 0.604,
      "rep_ticket": "TK00009",
      "rep_text": "系统强制改密码和我的老密码冲突，能申请例外吗"
    },
    {
      "rank": 5,
      "intent": "社保转移办理",
      "size": 25,
      "cover_median": 0.6083,
      "rep_ticket": "TK00023",
      "rep_text": "跨省社保转移多久能到账，麻烦帮忙确认一下流程"
    },
    {
      "rank": 6,
      "intent": "社保转移办理",
      "size": 29,
      "cover_median": 0.6175,
      "rep_ticket": "TK00046",
      "rep_text": "社保转移现在要线上还是线下，麻烦帮忙确认一下流程"
    },
    {
      "rank": 7,
      "intent": "终端病毒处置",
      "size": 21,
      "cover_median": 0.6179,
      "rep_ticket": "TK00279",
      "rep_text": "终端要隔离重装吗，麻烦帮忙确认一下流程"
    }
  ],
  "corrupt": [
    {
      "doc_id": "DOC0241",
      "title": "关于客户信息查询授权适用范围的说明（第21版）",
      "category": "客户服务",
      "last_modified": "2024-05-26",
      "risk_score": 8,
      "rule_hits": "R1_正文过期日期|R2_更新时间超18个月|R3_正文含绝对过期年份|R4_同类存在更新文档",
      "reasons": "正文含早于2026年的日期表述+过期标记词; last_modified=2024-05-26, 距基准日超过18个月; 正文含绝对过期年份 [2024]; 同'客户服务'下有 9 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0171",
      "title": "关于合同用印审批所需材料的说明（第15版）",
      "category": "采购合同",
      "last_modified": "2025-08-13",
      "risk_score": 6,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'采购合同'下有 1 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0067",
      "title": "关于考勤异常处理常见错误的说明（第6版）",
      "category": "人事行政",
      "last_modified": "2025-07-03",
      "risk_score": 6,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'人事行政'下有 1 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0080",
      "title": "关于离职交接手续责任分工的说明（第7版）",
      "category": "人事行政",
      "last_modified": "2025-04-30",
      "risk_score": 6,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'人事行政'下有 7 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0032",
      "title": "关于预算追加流程责任分工的说明（第3版）",
      "category": "财务管理",
      "last_modified": "2025-08-10",
      "risk_score": 6,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'财务管理'下有 3 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0002",
      "title": "关于差旅费报销适用范围的说明（更新第1版）",
      "category": "财务管理",
      "last_modified": "2025-07-15",
      "risk_score": 6,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'财务管理'下有 1 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0243",
      "title": "关于客户信息查询授权所需材料的说明（第21版）",
      "category": "客户服务",
      "last_modified": "2026-02-13",
      "risk_score": 5,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2025]"
    },
    {
      "doc_id": "DOC0290",
      "title": "关于数据分类分级办理时限的说明（第25版）",
      "category": "信息安全",
      "last_modified": "2026-06-18",
      "risk_score": 5,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]"
    },
    {
      "doc_id": "DOC0207",
      "title": "关于保密协议签署所需材料的说明（第18版）",
      "category": "法务合规",
      "last_modified": "2026-03-18",
      "risk_score": 5,
      "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份",
      "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]"
    },
    {
      "doc_id": "DOC0101",
      "title": "关于VPN远程接入申请额度标准的说明（第9版）",
      "category": "信息技术",
      "last_modified": "2025-01-05",
      "risk_score": 3,
      "rule_hits": "R2_更新时间超18个月|R4_同类存在更新文档",
      "reasons": "last_modified=2025-01-05, 距基准日超过18个月; 同'信息技术'下有 7 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0119",
      "title": "关于邮箱账号开通查询统计的说明（第10版）",
      "category": "信息技术",
      "last_modified": "2022-01-02",
      "risk_score": 3,
      "rule_hits": "R2_更新时间超18个月|R4_同类存在更新文档",
      "reasons": "last_modified=2022-01-02, 距基准日超过18个月; 同'信息技术'下有 14 篇更新且标题重合的文档"
    },
    {
      "doc_id": "DOC0283",
      "title": "关于终端病毒处置常见错误的说明（第24版）",
      "category": "信息安全",
      "last_modified": "2022-06-06",
      "risk_score": 3,
      "rule_hits": "R2_更新时间超18个月|R4_同类存在更新文档",
      "reasons": "last_modified=2022-06-06, 距基准日超过18个月; 同'信息安全'下有 12 篇更新且标题重合的文档"
    }
  ],
  "dups": [
    {
      "group": 1,
      "size": 3,
      "primary_doc": "DOC0003",
      "member_docs": "DOC0001|DOC0002|DOC0003",
      "max_sim": 0.9824
    },
    {
      "group": 2,
      "size": 3,
      "primary_doc": "DOC0014",
      "member_docs": "DOC0013|DOC0014|DOC0015",
      "max_sim": 0.983
    },
    {
      "group": 3,
      "size": 3,
      "primary_doc": "DOC0026",
      "member_docs": "DOC0025|DOC0026|DOC0027",
      "max_sim": 0.9845
    },
    {
      "group": 4,
      "size": 3,
      "primary_doc": "DOC0039",
      "member_docs": "DOC0037|DOC0038|DOC0039",
      "max_sim": 0.9821
    },
    {
      "group": 5,
      "size": 3,
      "primary_doc": "DOC0050",
      "member_docs": "DOC0049|DOC0050|DOC0051",
      "max_sim": 0.984
    },
    {
      "group": 6,
      "size": 2,
      "primary_doc": "DOC0062",
      "member_docs": "DOC0061|DOC0062",
      "max_sim": 0.9833
    },
    {
      "group": 7,
      "size": 2,
      "primary_doc": "DOC0074",
      "member_docs": "DOC0073|DOC0074",
      "max_sim": 0.9841
    },
    {
      "group": 8,
      "size": 2,
      "primary_doc": "DOC0086",
      "member_docs": "DOC0085|DOC0086",
      "max_sim": 0.9783
    },
    {
      "group": 9,
      "size": 2,
      "primary_doc": "DOC0098",
      "member_docs": "DOC0097|DOC0098",
      "max_sim": 0.9731
    },
    {
      "group": 10,
      "size": 2,
      "primary_doc": "DOC0110",
      "member_docs": "DOC0109|DOC0110",
      "max_sim": 0.9821
    },
    {
      "group": 11,
      "size": 2,
      "primary_doc": "DOC0122",
      "member_docs": "DOC0121|DOC0122",
      "max_sim": 0.9819
    },
    {
      "group": 12,
      "size": 2,
      "primary_doc": "DOC0134",
      "member_docs": "DOC0133|DOC0134",
      "max_sim": 0.9821
    },
    {
      "group": 13,
      "size": 2,
      "primary_doc": "DOC0146",
      "member_docs": "DOC0145|DOC0146",
      "max_sim": 0.9814
    },
    {
      "group": 14,
      "size": 2,
      "primary_doc": "DOC0158",
      "member_docs": "DOC0157|DOC0158",
      "max_sim": 0.9768
    },
    {
      "group": 15,
      "size": 2,
      "primary_doc": "DOC0170",
      "member_docs": "DOC0169|DOC0170",
      "max_sim": 0.9782
    },
    {
      "group": 16,
      "size": 2,
      "primary_doc": "DOC0182",
      "member_docs": "DOC0181|DOC0182",
      "max_sim": 0.9791
    },
    {
      "group": 17,
      "size": 2,
      "primary_doc": "DOC0194",
      "member_docs": "DOC0193|DOC0194",
      "max_sim": 0.9777
    },
    {
      "group": 18,
      "size": 2,
      "primary_doc": "DOC0206",
      "member_docs": "DOC0205|DOC0206",
      "max_sim": 0.9545
    },
    {
      "group": 19,
      "size": 2,
      "primary_doc": "DOC0218",
      "member_docs": "DOC0217|DOC0218",
      "max_sim": 0.9839
    },
    {
      "group": 20,
      "size": 2,
      "primary_doc": "DOC0230",
      "member_docs": "DOC0229|DOC0230",
      "max_sim": 0.982
    },
    {
      "group": 21,
      "size": 2,
      "primary_doc": "DOC0242",
      "member_docs": "DOC0241|DOC0242",
      "max_sim": 0.9805
    },
    {
      "group": 22,
      "size": 2,
      "primary_doc": "DOC0254",
      "member_docs": "DOC0253|DOC0254",
      "max_sim": 0.9766
    }
  ],
  "metrics": {
    "n_docs": 300,
    "n_tickets": 2000,
    "n_passages": 1852,
    "encode_seconds": 14.61,
    "gap": {
      "threshold": 0.62,
      "gap_clusters": 7,
      "detected_intents": 5,
      "precision": 0.8,
      "recall": 0.8,
      "f1": 0.8,
      "min_cluster_size": 5,
      "n_clusters": 95,
      "n_noise": 0
    },
    "corrupt": {
      "threshold": 3,
      "detected": 69,
      "embedded": 62,
      "tp": 62,
      "fp": 7,
      "fn": 0,
      "fp_from_control": 6,
      "fp_from_dup_inherit": 1,
      "fp_other": 0,
      "precision": 0.8986,
      "recall": 1,
      "f1": 0.9466,
      "seconds": 0.4,
      "rule_weight": {
        "R1": 3,
        "R2": 2,
        "R3": 2,
        "R4": 1
      },
      "rule_hit_counts": {
        "R1": 32,
        "R2": 38,
        "R3": 32,
        "R4": 88
      },
      "score_hist": {
        "0": 186,
        "1": 45,
        "3": 37,
        "5": 26,
        "6": 5,
        "8": 1
      }
    },
    "dup": {
      "threshold": 0.95,
      "dup_groups": 22,
      "detected_docs": 49,
      "group_precision": 1,
      "group_recall": 1,
      "group_f1": 1,
      "seconds": 0
    },
    "total_seconds": 3.09
  }
};

window.KB = KB;
