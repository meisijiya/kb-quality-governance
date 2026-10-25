/* 本文件是 poc/kbgovernance/ 下机读产物的内联快照，取值未作任何改写。
 * 数据源：gap_intents_best.csv / gap_clusters_best.csv / corrupt_docs.csv /
 * dup_groups_best.csv / metrics.json
 * 仅保留规格附录 A 允许透出的字段；评测依据列与归因列未纳入。
 * audit 段是评审要求补充披露的口径数字，同样逐条对应产物文件，由
 * check_prototype.py 第 5 节核对。
 */

const KB = {
  "gaps": [
    { "intent": "公积金提取材料", "n_clusters": 3, "min_cover_median": 0.5629, "total_tickets": 76, "rep_ticket": "TK00119", "rep_text": "租房提取和购房提取材料一样吗，麻烦帮忙确认一下流程" },
    { "intent": "海外出差报销标准", "n_clusters": 3, "min_cover_median": 0.5712, "total_tickets": 78, "rep_ticket": "TK00004", "rep_text": "去东南亚出差的住宿标准是多少，麻烦帮忙确认一下流程" },
    { "intent": "密码策略例外申请", "n_clusters": 3, "min_cover_median": 0.604, "total_tickets": 62, "rep_ticket": "TK00009", "rep_text": "系统强制改密码和我的老密码冲突，能申请例外吗" },
    { "intent": "社保转移办理", "n_clusters": 3, "min_cover_median": 0.6083, "total_tickets": 85, "rep_ticket": "TK00023", "rep_text": "跨省社保转移多久能到账，麻烦帮忙确认一下流程" },
    { "intent": "终端病毒处置", "n_clusters": 3, "min_cover_median": 0.6179, "total_tickets": 63, "rep_ticket": "TK00279", "rep_text": "终端要隔离重装吗，麻烦帮忙确认一下流程" }
  ],
  "corrupt": [
    { "doc_id": "DOC0241", "title": "关于客户信息查询授权适用范围的说明（第21版）", "category": "客户服务", "last_modified": "2024-05-26", "risk_score": 8, "rule_hits": "R1_正文过期日期|R2_更新时间超18个月|R3_正文含绝对过期年份|R4_同类存在更新文档", "reasons": "正文含早于2026年的日期表述+过期标记词; last_modified=2024-05-26, 距基准日超过18个月; 正文含绝对过期年份 [2024]; 同'客户服务'下有 9 篇更新且标题重合的文档", "cause_score_content_expiry": 5, "cause_score_maintenance": 3 },
    { "doc_id": "DOC0171", "title": "关于合同用印审批所需材料的说明（第15版）", "category": "采购合同", "last_modified": "2025-08-13", "risk_score": 6, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'采购合同'下有 1 篇更新且标题重合的文档", "cause_score_content_expiry": 5, "cause_score_maintenance": 1 },
    { "doc_id": "DOC0067", "title": "关于考勤异常处理常见错误的说明（第6版）", "category": "人事行政", "last_modified": "2025-07-03", "risk_score": 6, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'人事行政'下有 1 篇更新且标题重合的文档", "cause_score_content_expiry": 5, "cause_score_maintenance": 1 },
    { "doc_id": "DOC0080", "title": "关于离职交接手续责任分工的说明（第7版）", "category": "人事行政", "last_modified": "2025-04-30", "risk_score": 6, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'人事行政'下有 7 篇更新且标题重合的文档", "cause_score_content_expiry": 5, "cause_score_maintenance": 1 },
    { "doc_id": "DOC0032", "title": "关于预算追加流程责任分工的说明（第3版）", "category": "财务管理", "last_modified": "2025-08-10", "risk_score": 6, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'财务管理'下有 3 篇更新且标题重合的文档", "cause_score_content_expiry": 5, "cause_score_maintenance": 1 },
    { "doc_id": "DOC0002", "title": "关于差旅费报销适用范围的说明（更新第1版）", "category": "财务管理", "last_modified": "2025-07-15", "risk_score": 6, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份|R4_同类存在更新文档", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]; 同'财务管理'下有 1 篇更新且标题重合的文档", "cause_score_content_expiry": 5, "cause_score_maintenance": 1 },
    { "doc_id": "DOC0243", "title": "关于客户信息查询授权所需材料的说明（第21版）", "category": "客户服务", "last_modified": "2026-02-13", "risk_score": 5, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2025]", "cause_score_content_expiry": 5, "cause_score_maintenance": 0 },
    { "doc_id": "DOC0290", "title": "关于数据分类分级办理时限的说明（第25版）", "category": "信息安全", "last_modified": "2026-06-18", "risk_score": 5, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]", "cause_score_content_expiry": 5, "cause_score_maintenance": 0 },
    { "doc_id": "DOC0207", "title": "关于保密协议签署所需材料的说明（第18版）", "category": "法务合规", "last_modified": "2026-03-18", "risk_score": 5, "rule_hits": "R1_正文过期日期|R3_正文含绝对过期年份", "reasons": "正文含早于2026年的日期表述+过期标记词; 正文含绝对过期年份 [2024]", "cause_score_content_expiry": 5, "cause_score_maintenance": 0 },
    { "doc_id": "DOC0101", "title": "关于VPN远程接入申请额度标准的说明（第9版）", "category": "信息技术", "last_modified": "2025-01-05", "risk_score": 3, "rule_hits": "R2_更新时间超18个月|R4_同类存在更新文档", "reasons": "last_modified=2025-01-05, 距基准日超过18个月; 同'信息技术'下有 7 篇更新且标题重合的文档", "cause_score_content_expiry": 0, "cause_score_maintenance": 3 },
    { "doc_id": "DOC0119", "title": "关于邮箱账号开通查询统计的说明（第10版）", "category": "信息技术", "last_modified": "2022-01-02", "risk_score": 3, "rule_hits": "R2_更新时间超18个月|R4_同类存在更新文档", "reasons": "last_modified=2022-01-02, 距基准日超过18个月; 同'信息技术'下有 14 篇更新且标题重合的文档", "cause_score_content_expiry": 0, "cause_score_maintenance": 3 },
    { "doc_id": "DOC0283", "title": "关于终端病毒处置常见错误的说明（第24版）", "category": "信息安全", "last_modified": "2022-06-06", "risk_score": 3, "rule_hits": "R2_更新时间超18个月|R4_同类存在更新文档", "reasons": "last_modified=2022-06-06, 距基准日超过18个月; 同'信息安全'下有 12 篇更新且标题重合的文档", "cause_score_content_expiry": 0, "cause_score_maintenance": 3 }
  ],
  "dups": [
    { "group": 1, "size": 3, "primary_doc": "DOC0003", "member_docs": "DOC0001|DOC0002|DOC0003", "max_sim": 0.9824 },
    { "group": 2, "size": 3, "primary_doc": "DOC0014", "member_docs": "DOC0013|DOC0014|DOC0015", "max_sim": 0.983 },
    { "group": 3, "size": 3, "primary_doc": "DOC0026", "member_docs": "DOC0025|DOC0026|DOC0027", "max_sim": 0.9845 },
    { "group": 4, "size": 3, "primary_doc": "DOC0039", "member_docs": "DOC0037|DOC0038|DOC0039", "max_sim": 0.9821 },
    { "group": 5, "size": 3, "primary_doc": "DOC0050", "member_docs": "DOC0049|DOC0050|DOC0051", "max_sim": 0.984 },
    { "group": 6, "size": 2, "primary_doc": "DOC0062", "member_docs": "DOC0061|DOC0062", "max_sim": 0.9833 },
    { "group": 7, "size": 2, "primary_doc": "DOC0074", "member_docs": "DOC0073|DOC0074", "max_sim": 0.9841 },
    { "group": 8, "size": 2, "primary_doc": "DOC0086", "member_docs": "DOC0085|DOC0086", "max_sim": 0.9783 },
    { "group": 9, "size": 2, "primary_doc": "DOC0098", "member_docs": "DOC0097|DOC0098", "max_sim": 0.9731 },
    { "group": 10, "size": 2, "primary_doc": "DOC0110", "member_docs": "DOC0109|DOC0110", "max_sim": 0.9821 },
    { "group": 11, "size": 2, "primary_doc": "DOC0122", "member_docs": "DOC0121|DOC0122", "max_sim": 0.9819 },
    { "group": 12, "size": 2, "primary_doc": "DOC0134", "member_docs": "DOC0133|DOC0134", "max_sim": 0.9821 },
    { "group": 13, "size": 2, "primary_doc": "DOC0146", "member_docs": "DOC0145|DOC0146", "max_sim": 0.9814 },
    { "group": 14, "size": 2, "primary_doc": "DOC0158", "member_docs": "DOC0157|DOC0158", "max_sim": 0.9768 },
    { "group": 15, "size": 2, "primary_doc": "DOC0170", "member_docs": "DOC0169|DOC0170", "max_sim": 0.9782 },
    { "group": 16, "size": 2, "primary_doc": "DOC0182", "member_docs": "DOC0181|DOC0182", "max_sim": 0.9791 },
    { "group": 17, "size": 2, "primary_doc": "DOC0194", "member_docs": "DOC0193|DOC0194", "max_sim": 0.9777 },
    { "group": 18, "size": 2, "primary_doc": "DOC0206", "member_docs": "DOC0205|DOC0206", "max_sim": 0.9545 },
    { "group": 19, "size": 2, "primary_doc": "DOC0218", "member_docs": "DOC0217|DOC0218", "max_sim": 0.9839 },
    { "group": 20, "size": 2, "primary_doc": "DOC0230", "member_docs": "DOC0229|DOC0230", "max_sim": 0.982 },
    { "group": 21, "size": 2, "primary_doc": "DOC0242", "member_docs": "DOC0241|DOC0242", "max_sim": 0.9805 },
    { "group": 22, "size": 2, "primary_doc": "DOC0254", "member_docs": "DOC0253|DOC0254", "max_sim": 0.9766 }
  ],
  "metrics": {
    "n_docs": 300,
    "n_tickets": 2000,
    "n_passages": 1852,
    "encode_seconds": 14.61,
    "has_ground_truth": true,
    "gap": {
      "threshold": 0.62,
      "gap_clusters": 7,
      "detected_intents": 5,
      "precision": 0.8,
      "recall": 0.8,
      "f1": 0.8,
      "min_cluster_size": 5,
      "n_clusters": 95,
      "n_noise": 0,
      "n_gap_intents": 5,
      "gap_intents": [
        "公积金提取材料",
        "海外出差报销标准",
        "密码策略例外申请",
        "社保转移办理",
        "终端病毒处置"
      ]
    },
    "corrupt": {
      "threshold": 3,
      "embedded": 62,
      "detected": 69,
      "covered": 62,
      "fp": 7,
      "seconds": 0.51,
      "rule_weight": {
        "R1_正文过期日期": 3,
        "R2_更新时间超18个月": 2,
        "R3_正文含绝对过期年份": 2,
        "R4_同类存在更新文档": 1
      },
      "rule_hit_counts": {
        "R1_正文过期日期": 32,
        "R2_更新时间超18个月": 38,
        "R3_正文含绝对过期年份": 32,
        "R4_同类存在更新文档": 88
      },
      "score_hist": {
        "0": 186,
        "1": 45,
        "3": 37,
        "5": 26,
        "6": 5,
        "8": 1
      },
      "by_cause": {
        "content_expiry": {
          "label": "内容过期",
          "rules": [
            "R1_正文过期日期",
            "R3_正文含绝对过期年份"
          ],
          "threshold": 3,
          "planted": 32,
          "truth": 32,
          "detected": 32,
          "tp": 32,
          "fp": 0,
          "fn": 0,
          "precision": 1.0,
          "recall": 1.0,
          "f1": 1.0,
          "fp_attribution": {}
        },
        "maintenance": {
          "label": "维护周期",
          "rules": [
            "R2_更新时间超18个月",
            "R4_同类存在更新文档"
          ],
          "threshold": 3,
          "planted": 30,
          "truth": 31,
          "detected": 38,
          "tp": 31,
          "fp": 7,
          "fn": 0,
          "precision": 0.8158,
          "recall": 1.0,
          "f1": 0.8986,
          "fp_attribution": {
            "dup_inherited_stale": 1,
            "control_stale": 6
          }
        }
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
    "total_seconds": 3.75
  },
  "audit": {
    "run": {
      "built_at": "2026-10-25T12:25:25+08:00",
      "artifacts_fingerprint": "a53ee95577ba3d80",
      "source": "poc/kbgovernance/repro_check.json"
    },
    "gap_pool": {
      "clusters": 95,
      "intents": 30,
      "shown_clusters": 7,
      "shown_intents": 5,
      "source": "poc/kbgovernance/gap_clusters_best.csv"
    },
    "gap_threshold_scan": [
      { "threshold": 0.6, "gap_clusters": 3, "detected_intents": 2, "precision": 1.0, "recall": 0.4, "f1": 0.5714 },
      { "threshold": 0.62, "gap_clusters": 7, "detected_intents": 5, "precision": 0.8, "recall": 0.8, "f1": 0.8 },
      { "threshold": 0.64, "gap_clusters": 15, "detected_intents": 10, "precision": 0.5, "recall": 1.0, "f1": 0.6667 },
      { "threshold": 0.66, "gap_clusters": 27, "detected_intents": 16, "precision": 0.3125, "recall": 1.0, "f1": 0.4762 }
    ],
    "gap_threshold_scan_source": "poc/kbgovernance/gap_threshold.csv (min_cluster_size=5)",
    "gap_near_miss": [
      { "cluster_id": 13, "intent": "密码策略例外申请", "size": 21, "cover_median": 0.624 },
      { "cluster_id": 7, "intent": "社保转移办理", "size": 31, "cover_median": 0.6272 },
      { "cluster_id": 84, "intent": "考勤异常处理", "size": 28, "cover_median": 0.6278 },
      { "cluster_id": 21, "intent": "门禁权限申请", "size": 23, "cover_median": 0.6287 },
      { "cluster_id": 3, "intent": "数据导出权限申请", "size": 21, "cover_median": 0.6342 },
      { "cluster_id": 14, "intent": "密码策略例外申请", "size": 22, "cover_median": 0.635 },
      { "cluster_id": 89, "intent": "供应商准入申请", "size": 17, "cover_median": 0.6352 },
      { "cluster_id": 34, "intent": "采购比价流程", "size": 9, "cover_median": 0.6398 },
      { "cluster_id": 45, "intent": "公积金提取材料", "size": 30, "cover_median": 0.643 },
      { "cluster_id": 31, "intent": "发票合规校验", "size": 24, "cover_median": 0.6481 }
    ],
    "gap_near_miss_total": 88,
    "gap_near_miss_source": "poc/kbgovernance/gap_clusters_best.csv (cover_median >= 0.62 的行)",
    "dup_threshold_scan": [
      { "threshold": 0.85, "dup_groups": 23, "detected_docs": 223, "group_f1": 0.1778, "doc_f1": 0.3603 },
      { "threshold": 0.9, "dup_groups": 32, "detected_docs": 77, "group_f1": 0.7037, "doc_f1": 0.7778 },
      { "threshold": 0.95, "dup_groups": 22, "detected_docs": 49, "group_f1": 1.0, "doc_f1": 1.0 }
    ],
    "dup_threshold_scan_source": "poc/kbgovernance/dup_threshold.csv",
    "cover_stats": {
      "min": 0.5629,
      "mean": 0.6891,
      "max": 0.8294,
      "sd": 0.0529
    },
    "cover_stats_source": "poc/kbgovernance/standardize/scenario_meta.json (cover_stats.alpha)",
    "corrupt_rule_combos": [
      { "rules": "R1+R2+R3+R4", "docs": 1 },
      { "rules": "R1+R3+R4", "docs": 5 },
      { "rules": "R1+R3", "docs": 26 },
      { "rules": "R2+R4", "docs": 37 }
    ],
    "corrupt_rule_combos_source": "poc/kbgovernance/corrupt_docs.csv (risk_score >= 3 的行按规则命中组合分组)",
    "corrupt_sample": {
      "shown": 12,
      "total": 69,
      "combos": 4,
      "source": "poc/kbgovernance/corrupt_docs.csv"
    },
    "requirement": {
      "scan_seconds_max": 60,
      "page_response_seconds_max": 2,
      "source": "docs/技术方案/企业知识库质量治理系统技术方案.md（需求阈值，非实测）"
    },
    "products": {
      "gap": {
        "label": "知识缺口清单（业务意图级）",
        "path": "poc/kbgovernance/gap_intents_best.csv"
      },
      "gap_clusters": {
        "label": "知识缺口簇明细（内部量）",
        "path": "poc/kbgovernance/gap_clusters_best.csv"
      },
      "corrupt": {
        "label": "内容腐化清单",
        "path": "poc/kbgovernance/corrupt_docs.csv"
      },
      "dup": {
        "label": "重复冗余清单",
        "path": "poc/kbgovernance/dup_groups_best.csv"
      }
    }
  }
};

window.KB = KB;
