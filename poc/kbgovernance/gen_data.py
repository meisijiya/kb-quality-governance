# -*- coding: utf-8 -*-
"""
gen_data.py -- 生成企业知识库质量治理 PoC 的合成数据 + ground truth。

产出:
  docs.csv          300 篇知识库文档
  tickets.csv       2000 条客服工单
  ground_truth.json 真实缺陷清单（缺口意图 / 腐化文档 / 重复组）

可复现: random.seed(42) + np.random.seed(42)
"""
import csv
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

random.seed(42)
np.random.seed(42)

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DATE = date(2026, 10, 1)          # 判定"当前时间"的基准日
N_DOCS = 300
N_TICKETS = 2000

# ---------------------------------------------------------------- 缺陷(a) 知识缺口
GAP_INTENTS = [
    "社保转移办理",
    "公积金提取材料",
    "数据导出权限申请",
    "海外出差报销标准",
    "密码策略例外申请",
]

# ---------------------------------------------------------------- 25 个"已被覆盖"的意图
COVERED_INTENTS = [
    ("差旅费报销", "财务管理"), ("发票合规校验", "财务管理"),
    ("预算追加流程", "财务管理"), ("备用金管理", "财务管理"),
    ("入职材料办理", "人事行政"), ("考勤异常处理", "人事行政"),
    ("离职交接手续", "人事行政"), ("办公用品领用", "人事行政"),
    ("VPN远程接入申请", "信息技术"), ("邮箱账号开通", "信息技术"),
    ("系统权限开通", "信息技术"), ("打印机故障报修", "信息技术"),
    ("供应商准入申请", "采购合同"), ("采购比价流程", "采购合同"),
    ("合同用印审批", "采购合同"),
    ("合同条款审查", "法务合规"), ("印章使用登记", "法务合规"),
    ("保密协议签署", "法务合规"),
    ("投诉工单处理时限", "客户服务"), ("服务等级协议赔付", "客户服务"),
    ("客户信息查询授权", "客户服务"),
    ("会议室预订规则", "后勤保障"), ("门禁权限申请", "后勤保障"),
    ("终端病毒处置", "信息安全"), ("数据分类分级", "信息安全"),
]

# 工单权重（覆盖意图）
COVERED_WEIGHT = {
    "差旅费报销": 0.052, "发票合规校验": 0.040, "预算追加流程": 0.026,
    "备用金管理": 0.028, "入职材料办理": 0.036, "考勤异常处理": 0.045,
    "离职交接手续": 0.030, "办公用品领用": 0.035, "VPN远程接入申请": 0.034,
    "邮箱账号开通": 0.031, "系统权限开通": 0.038, "打印机故障报修": 0.042,
    "供应商准入申请": 0.022, "采购比价流程": 0.020, "合同用印审批": 0.019,
    "合同条款审查": 0.021, "印章使用登记": 0.025, "保密协议签署": 0.018,
    "投诉工单处理时限": 0.033, "服务等级协议赔付": 0.017,
    "客户信息查询授权": 0.024, "会议室预订规则": 0.047,
    "门禁权限申请": 0.030, "终端病毒处置": 0.028, "数据分类分级": 0.023,
}
GAP_WEIGHT = {
    "社保转移办理": 0.042, "公积金提取材料": 0.040, "数据导出权限申请": 0.038,
    "海外出差报销标准": 0.036, "密码策略例外申请": 0.032,
}

# ---------------------------------------------------------------- 意图画像
PROFILES = {
    "差旅费报销": ("财务部", "出差审批人", "财务共享中心", ["行程单", "住宿发票", "费用明细表"], ["3000", "5000", "8000"], "次月5日", "12", "跨境出差"),
    "发票合规校验": ("财务部", "票据审核岗", "税务共享中心", ["发票抬头", "税号校验", "查验码"], ["全月", "单张"], "10", "8", "增值税专用发票"),
    "预算追加流程": ("财务管理部", "预算管理岗", "财务总监", ["预算测算表", "追加事由说明"], ["10%", "20%", "30%"], "每月25日", "24", "跨年度预算"),
    "备用金管理": ("财务部", "出纳岗", "部门负责人", ["借款单", "还款计划"], ["5000", "10000", "20000"], "季度末", "30", "备用金超期"),
    "入职材料办理": ("人力资源部", "招聘专员", "用人部门主管", ["身份证明", "学历证书", "离职证明", "体检报告"], ["5", "10", "15"], "每周五", "60", "背景调查未通过"),
    "考勤异常处理": ("人力资源部", "考勤专员", "部门主管", ["打卡记录", "加班申请单", "外勤签到"], ["当日", "本周"], "每月1日", "36", "漏打卡与外勤"),
    "离职交接手续": ("人力资源部", "人事专员", "离职员工主管", ["交接清单", "资产归还单", "保密确认书"], ["5", "10", "20"], "离职当日", "24", "试用期离职"),
    "办公用品领用": ("行政部", "行政前台", "部门助理", ["领用申请单", "库存台账"], ["每季度", "每月"], "每月28日", "48", "大批量集中领用"),
    "VPN远程接入申请": ("信息技术部", "IT服务台", "网络管理员", ["申请工单", "VPN客户端安装包"], ["3", "5", "10"], "每周三", "48", "境外网络访问"),
    "邮箱账号开通": ("信息技术部", "IT服务台", "部门主管", ["入职审批单", "邮箱命名规范"], ["当日", "2", "3"], "每周五", "12", "同名账号冲突"),
    "系统权限开通": ("信息技术部", "系统管理员", "业务系统负责人", ["权限申请单", "审批链截图"], ["1", "3", "5"], "每日", "24", "临时提权"),
    "打印机故障报修": ("信息技术部", "IT服务台", "行政主管", ["故障描述", "设备编号", "报修单"], ["当日", "次日"], "每周五", "12", "耗材缺纸与卡纸"),
    "供应商准入申请": ("采购部", "采购专员", "采购经理", ["营业执照", "资质证书", "供应商承诺书"], ["10", "20", "30"], "每月20日", "36", "供应商黑名单"),
    "采购比价流程": ("采购部", "采购专员", "招标负责人", ["三家报价单", "比价表"], ["5000", "20000", "50000"], "每月15日", "24", "单一来源采购"),
    "合同用印审批": ("采购部", "合同管理员", "法务负责人", ["用印申请单", "合同终稿"], ["1", "2", "3"], "每工作日", "24", "骑缝章与电子签"),
    "合同条款审查": ("法务合规部", "法务专员", "合规总监", ["合同文本", "条款审查意见"], ["5", "10", "15"], "每周五", "30", "对方拒绝修改条款"),
    "印章使用登记": ("法务合规部", "印章管理员", "综合办公室主任", ["用印登记簿", "用印申请"], ["当日", "次日"], "每工作日", "60", "印章外借"),
    "保密协议签署": ("法务合规部", "法务专员", "人力资源部", ["保密协议正本", "签署回执"], ["3", "5", "7"], "每月末", "36", "涉密岗位调岗"),
    "投诉工单处理时限": ("客户服务部", "客服组长", "服务经理", ["投诉记录", "回访记录"], ["24", "48", "72"], "每工作日", "36", "重复投诉与升级"),
    "服务等级协议赔付": ("客户服务部", "服务经理", "财务部", ["故障报告", "赔付计算表"], ["月度", "季度"], "每月10日", "24", "第三方责任故障"),
    "客户信息查询授权": ("客户服务部", "客服专员", "信息安全部", ["授权书", "查询事由"], ["3", "5", "7"], "每工作日", "12", "批量客户信息调取"),
    "会议室预订规则": ("行政部", "行政前台", "部门主管", ["预订记录", "会议室使用登记表"], ["提前1天", "提前3天", "提前7天"], "每周一", "12", "大型会议与培训"),
    "门禁权限申请": ("行政部", "安保主管", "部门主管", ["门禁申请单", "身份证明复印件"], ["1", "3", "5"], "每工作日", "12", "外籍人员来访"),
    "终端病毒处置": ("信息安全部", "安全工程师", "IT服务台", ["病毒告警日志", "隔离申请单"], ["2", "4", "8"], "每日", "36", "勒索软件与挖矿程序"),
    "数据分类分级": ("信息安全部", "安全工程师", "数据合规岗", ["分级清单", "数据资产台账"], ["一级", "二级", "三级"], "每季度", "60", "历史遗留数据"),
}

# ---------------------------------------------------------------- 12 类文档模板
ASPECTS = ["适用范围", "办理时限", "所需材料", "审批流程", "额度标准",
           "系统操作", "常见错误", "责任分工", "记录归档", "特殊情形",
           "查询统计", "违规处理"]


def render_sentences(aspect, prof, variant):
    """为某个 aspect 生成 4 句"业务专属"正文。

    设计约束：正文绝大部分必须是意图/aspect 专属表述，
    共用套话越少，语义向量才越能反映文档真实主题（否则基线相似度过高，
    知识缺口信号会被淹没）。
    """
    dept, role1, role2, mats, amts, when, years, special = prof
    aspect_name = ASPECTS[aspect]
    mat = random.choice(mats)
    mat2 = random.choice([m for m in mats if m != mat]) if len(mats) > 1 else mat
    amt = random.choice(amts)
    k = variant
    T = {
        0: [f"{aspect_name}限于{dept}归口业务，总部与各分支机构一律适用同一口径。",
            f"第三方代办的，须在委托书中写明本条适用范围，超出委托范围的由受托方自行承担后果。",
            f"境外机构参照本条执行时，{role1}负责逐条解释，不得自行变通。",
            f"本条与上级文件冲突的，以上级文件为准并同步修订本条。"],
        1: [f"{aspect_name}以{when}为最后期限，逾期系统关闭入口且不受理补办。",
            f"遇节假日顺延至下一工作日，跨年度事项顺延至新年度第一个工作周期。",
            f"申请人在期限内撤回后可重新提交，{role1}须在撤回后{k}小时内释放占用名额。",
            f"确有不可抗力需延期的，须在期限届满前提交书面延期说明。"],
        2: [f"办理须提交{mat}；涉及金额或期限的另需附{mat2}作为佐证。",
            f"材料须为原件或加盖公章的复印件，扫描件分辨率不低于可辨识表单号的程度。",
            f"材料与系统既有信息冲突时，以更严格者为准，并退回申请人确认。",
            f"{role1}对材料完整性负首责，材料缺失不得口头放行。"],
        3: [f"由{role1}初审、{role2}复核，两个环节均通过后方可进入执行环节。",
            f"金额或影响面超限的，须增加一级会签，由{dept}负责人线下确认。",
            f"任一环节退回须注明退回理由，申请人补正后重新提交，审批留痕不可撤销。",
            f"审批人休假期间按既定代理顺序转办，代理期间的决定与本人签字具有同等效力。"],
        4: [f"额度为{amt}，超出部分逐项说明事由并附第三方佐证。",
            f"额度按自然周期重置，未使用部分不得结转至下一周期。",
            f"拆分业务以规避额度的，按合并后金额重新适用本标准并追责。",
            f"标准由{role2}按年度复核，复核结果自次月起执行。"],
        5: [f"在门户{dept}工作台选择本条业务类型，填报后点击提交即发起。",
            f"填报字段带星号的为必填项，{mat}需在附件区上传。",
            f"提交后可在待办列表撤回，撤回后重新提交将重新排队。",
            f"系统维护窗口内暂停受理，{role1}会在公告栏提前一个工作日通知。"],
        6: [f"高频问题有三类：填报错项、附件缺失、状态未同步，按此顺序自查。",
            f"错项多因口径理解偏差，{role1}负责在系统提示中给出示例值。",
            f"附件缺失占咨询量的多数，{role2}抽查发现后可退回并计入部门考核。",
            f"自查无果的带工单号提交服务台，服务台{when}前反馈结论。"],
        7: [f"责任部门为{dept}，各岗位按分工落实，不得以口头约定替代书面确认。",
            f"{role1}负责日常解释口径，{role2}负责例外审批。",
            f"两者意见不一致的，以部门例会决议为准，并同步更新本条。",
            f"岗位调整时由接任人重新确认职责，交接记录纳入{k}号台账。"],
        8: [f"记录留存不少于{years}个月，归档后只读，不得修改或物理销毁。",
            f"电子档与纸质档字段须一致，台账按季度核对并留存核对记录。",
            f"{role1}负责归档完整性，{role2}负责抽查，抽检比例不低于全部记录的十分之一。",
            f"超过留存期的资料由{dept}统一销毁并出具销毁清单。"],
        9: [f"遇{special}等特殊情形，须事先书面说明并经{role2}批准后执行。",
            f"特殊情形不适用批量简化流程，相关材料不得以电子签名替代。",
            f"未事先报批擅自适用特殊情形的，业务单据作废并重新走常规流程。",
            f"特殊情形处理结论须在月度例会上通报，供其他部门参照。"],
        10: [f"统计数据按周期更新，可在{dept}报表模块按条件筛选并导出。",
             f"报表口径以系统实时数为准，人工台账仅作辅助核对。",
             f"导出操作全程留痕，导出文件的接收方须在{k}个工作日内反馈使用情况。",
             f"{role1}每月核对一次报表与业务单据的差异并说明原因。"],
        11: [f"违反本条办理的，业务单据退回重办并记入当月考核。",
             f"情节严重的移交{dept}处理，相关责任人暂停本条业务办理权限。",
             f"违规记录累计达到阈值的，由{role2}出具整改报告后方可恢复权限。",
             f"因违规造成损失的，按公司责任追究办法另行追偿。"],
    }
    return T[aspect]


# ---------------------------------------------------------------- 工单话术模板
TICKET_TPL = {
    "差旅费报销": ["{n}出差回来发票还没交，OA报销一直提交不上去", "上周出差住宿费超标了还能报吗", "报销单被退回说缺少行程单，怎么办"],
    "发票合规校验": ["发票查验码提示无效，重新上传还是不行", "专票抬头写错了能重开吗", "系统说这张票查验重复"],
    "预算追加流程": ["项目超预算了想追加，走什么流程", "追加预算要交哪些测算表", "预算追加申请被驳回"],
    "备用金管理": ["备用金下个月还没还怎么核销", "借款单额度不够用能加吗", "备用金超期会有什么影响"],
    "入职材料办理": ["新员工入职材料还差哪些没交齐", "背调报告什么时候能交", "体检报告提交入口在哪"],
    "考勤异常处理": ["早上忘打卡了怎么补", "外勤没签到算缺勤吗", "加班时长没记上"],
    "离职交接手续": ["离职前还有哪些交接没做完", "离职了门禁什么时候销", "交接清单谁签字"],
    "办公用品领用": ["想领一箱打印纸怎么申请", "办公用品领用要填哪个台账", "上次领的还没登记"],
    "VPN远程接入申请": ["出差在外连不上内网，VPN申请怎么走", "VPN客户端装不上报错", "境外网络访问要单独审批吗"],
    "邮箱账号开通": ["新入职同事邮箱还没开通", "邮箱命名规范是怎样的", "同名账号冲突怎么处理"],
    "系统权限开通": ["业务系统里某个菜单点不开，权限怎么开", "临时提权申请要多久批", "权限开通后还是看不到数据"],
    "打印机故障报修": ["3楼打印机卡纸了报修没人来", "打印机耗材不足怎么申请", "设备编号找不到报修不了"],
    "供应商准入申请": ["新供应商想入库需要哪些资质", "准入申请提交后没进度", "供应商进黑名单了还能合作吗"],
    "采购比价流程": ["采购金额五万以上要怎么比价", "只有一家报价可以吗", "比价表模板在哪"],
    "合同用印审批": ["合同终稿要盖章怎么申请用印", "电子签和盖章哪个优先", "骑缝章要另外申请吗"],
    "合同条款审查": ["对方合同里有不利条款怎么办", "合同审查要提交几个工作日", "对方拒绝修改条款"],
    "印章使用登记": ["章要外借怎么登记", "用印登记簿在哪领", "盖完章的复印件需要留存吗"],
    "保密协议签署": ["保密协议签了没回执怎么办", "涉密岗位调岗要重签吗", "保密协议正本哪里交"],
    "投诉工单处理时限": ["客户投诉多久必须回访", "重复投诉升级要多久", "投诉记录在哪看"],
    "服务等级协议赔付": ["SLA故障造成损失怎么赔", "赔付计算表谁出", "第三方责任算不算SLA"],
    "客户信息查询授权": ["客户要求导出通话记录授权书怎么开", "批量查客户信息合规吗", "查询事由怎么写"],
    "会议室预订规则": ["会议室能提前多久订", "订了没人来要怎么处理", "大型会议要提前几天申请"],
    "门禁权限申请": ["新同事门禁卡怎么办", "外籍人员来访门禁怎么开通", "门禁卡丢了怎么挂失"],
    "终端病毒处置": ["电脑弹窗说中了勒索病毒", "安全告警日志里有挖矿程序", "终端要隔离重装吗"],
    "数据分类分级": ["业务数据算几级", "历史遗留数据要不要重新分级", "数据资产台账怎么维护"],
    # ---- 缺口意图（知识库完全没有覆盖）----
    "社保转移办理": ["想把社保转到新城市的公司，需要办什么手续", "社保转移现在要线上还是线下", "跨省社保转移多久能到账"],
    "公积金提取材料": ["公积金提取要提供哪些材料", "租房提取和购房提取材料一样吗", "提取申请提交后被说要补件"],
    "数据导出权限申请": ["想把后台数据导出成Excel需要什么权限", "导出权限审批找哪个岗", "批量导出数据要走什么流程"],
    "海外出差报销标准": ["去东南亚出差的住宿标准是多少", "海外出差津贴怎么算币种", "境外出差交通费能全报吗"],
    "密码策略例外申请": ["系统强制改密码和我的老密码冲突，能申请例外吗", "特殊系统密码复杂度要求能放宽吗", "密码过期太频繁影响办公"],
}


def pick_weighted(items, weights):
    vals = np.array([weights[i] for i in items], dtype=float)
    vals = vals / vals.sum()
    return random.choices(items, weights=vals.tolist(), k=1)[0]


# ================================================================ 生成文档
def gen_docs():
    docs = []
    doc_seq = 0
    per_intent = N_DOCS // len(COVERED_INTENTS)          # 12
    # 22 个意图的第 0、1 篇文档构成重复组；前 5 个意图再加上第 2 篇（三篇组）
    dup_intents = {int_[0] for int_ in COVERED_INTENTS[:22]}
    trip_intents = {int_[0] for int_ in COVERED_INTENTS[:5]}

    for idx, (intent, cat) in enumerate(COVERED_INTENTS):
        prof = PROFILES[intent]
        for k in range(per_intent):
            doc_seq += 1
            aspect = ASPECTS[k % len(ASPECTS)]
            sents = render_sentences(ASPECTS.index(aspect), prof, k)
            title = f"关于{intent}{aspect}的说明（第{idx + 1}版）"
            body = sents + [random.choice([
                f"本条为《{intent}操作手册》配套条款。",
                f"本条由{prof[0]}归口维护。",
                f"本条与《{intent}操作手册》正文配套执行。",
            ])]
            content = "".join(body)
            tmpl_len = len("".join(sents))
            docs.append({
                "doc_id": f"DOC{doc_seq:04d}",
                "title": title,
                "content": content,
                "category": cat,
                "intent": intent,
                "aspect": aspect,
                "_tmpl_len": tmpl_len,
                "created_at": None, "last_modified": None,
                "effective_date": None, "status": None,
                "ref_count": 0,
            })

        # ---- 缺陷(b) 重复冗余：把 doc1 改写成与 doc0 实质相同、措辞略异的版本
        if intent in dup_intents:
            d0, d1 = docs[-per_intent], docs[-per_intent + 1]
            a0 = render_sentences(ASPECTS.index(d0["aspect"]), prof, 0)
            tail0 = d0["content"][d0["_tmpl_len"]:]
            # 同 4 句正文，仅做 3 处措辞替换 + 前后两句调序
            s = list(a0)
            s[0] = s[0].replace("限于", "仅限").replace("适用", "适用") \
                          .replace("同一口径", "一致口径").replace("一并", "统一")
            s[1] = s[1].replace("须在", "应当").replace("写明", "载明").replace("超出", "超越")
            s[2] = s[2].replace("逐条解释", "逐项解释").replace("不得自行变通", "严禁自行变通")
            s[3] = s[3].replace("冲突的", "不一致的").replace("同步修订本条", "同步更新本条")
            d1["content"] = "".join([s[3], s[0], s[1], s[2]]) + tail0
            d1["title"] = d0["title"].replace("（第", "（更新第")
            d1["dup_of"] = d0["doc_id"]
        if intent in trip_intents:
            d2 = docs[-per_intent + 2]
            d0 = docs[-per_intent]
            a0 = render_sentences(ASPECTS.index(d0["aspect"]), prof, 0)
            tail0 = d0["content"][d0["_tmpl_len"]:]
            s = list(a0)
            s[0] = s[0].replace("限于", "只针对").replace("一律适用", "统一执行")
            s[1] = s[1].replace("须在", "应在").replace("写明", "注明").replace("超出", "超出")
            s[2] = s[2].replace("逐条解释", "逐条说明").replace("不得自行变通", "不得自行更改")
            s[3] = s[3].replace("冲突的", "相抵触的").replace("同步修订本条", "同步改写本条")
            d2["content"] = "".join([s[2], s[3], s[0], s[1]]) + tail0
            d2["title"] = d0["title"].replace("（第", "（修订第")
            d2["dup_of"] = d0["doc_id"]

    # ---- 日期字段
    # 现实企业知识库里绝大多数文档是近期维护的，只有少数长期没人碰。
    # 注意：这里必须用 random.random() 显式加权，早期版本误用 random.choice([a,b])
    # （两个元素等概率），导致一半文档被判为"超过18个月未更新"，规则 R2 完全失去区分度。
    # 另有 4% 是"自然陈旧但不算缺陷"的文档，用来给规则制造真实的边界模糊性。
    for i, d in enumerate(docs):
        if random.random() < 0.04:
            age = random.randint(600, 900)       # 4% 自然陈旧（非埋入缺陷）
            d["_control_sampled"] = True         # 只记录命中，不新增随机调用
        else:
            age = random.randint(20, 520)        # 96% 近期维护过
        lm = BASE_DATE - timedelta(days=age)
        ca = lm - timedelta(days=random.randint(60, 900))
        d["created_at"] = ca.isoformat()
        d["last_modified"] = lm.isoformat()
        d["effective_date"] = (ca + timedelta(days=random.randint(0, 30))).isoformat()
        d["status"] = random.choices(["生效", "已归档", "草稿"], weights=[0.82, 0.11, 0.07])[0]
        d["ref_count"] = random.randint(0, 190)

    # 主文档更"权威"：重复组内让 doc0 的 ref_count 高、last_modified 新。
    # 必须在"内容腐化"埋点之前执行，否则重复件会继承主文档的新时间，
    # 把已经埋下的 last_modified 缺陷覆盖掉（早期版本因此漏报 2 篇）。
    for d in docs:
        if d.get("dup_of"):
            src = next(x for x in docs if x["doc_id"] == d["dup_of"])
            d["ref_count"] = min(255, src["ref_count"] + random.randint(10, 60))
            d["last_modified"] = src["last_modified"]

    # ================================================================ 缺陷(c) 内容腐化
    STALE_TEXT = [
        "本政策自2024年1月1日起施行，原《{t}管理暂行办法》同时废止。",
        "该优惠活动截止2025年12月31日，逾期申请一律不予受理。",
        "本办法自2024年3月15日起施行，修订前版本自即日起失效。",
        "本条口径依据2024年度财务制度制定，该旧口径自2024年1月1日起施行，现已失效。",
        "该方案有效期至2025年6月30日，延期须另行报批。",
    ]
    all_ids = [d["doc_id"] for d in docs]
    random.shuffle(all_ids)
    corrupt_stale = set(all_ids[:32])                       # 32 篇正文含绝对过期年份
    corrupt_old = set(all_ids[32:32 + 30])                   # 30 篇 last_modified 早于 2024
    for d in docs:
        if d["doc_id"] in corrupt_stale:
            tpl = random.choice(STALE_TEXT).format(t=d["aspect"])
            d["content"] = d["content"] + tpl
            d["corrupt_reason"] = "stale_text"
        if d["doc_id"] in corrupt_old:
            y = random.choice([2022, 2023])
            mo = random.randint(1, 11)
            lm = date(y, mo, random.randint(1, 28))
            d["last_modified"] = lm.isoformat()
            d.setdefault("corrupt_reason", "")
            d["corrupt_reason"] = (d.get("corrupt_reason", "") + "+stale_mtime").strip("+")
        d.setdefault("corrupt_reason", "")

    # 主文档更"权威"的处理已提前到"内容腐化"之前（见上方注释）
    for d in docs:
        d["corrupt"] = 1 if d["corrupt_reason"] else 0
    return docs, corrupt_stale | corrupt_old


# ================================================================ 生成工单
def gen_tickets(docs):
    by_intent = {}
    for d in docs:
        by_intent.setdefault(d["intent"], []).append(d["doc_id"])

    covered = [i for i, _ in COVERED_INTENTS]
    tickets = []
    all_intents = covered + GAP_INTENTS
    weights = {**COVERED_WEIGHT, **GAP_WEIGHT}

    n = 0
    for k in range(N_TICKETS):
        intent = pick_weighted(all_intents, weights)
        tpl = random.choice(TICKET_TPL[intent])
        name = random.choice(["张", "李", "王", "刘", "陈", "杨", "赵", "周", "吴", "徐"])
        content = tpl.format(n=random.choice(["今天", "昨天", "上午", "下午", "周一", "本周", "上个月"]))
        content = content[:60] if len(content) > 58 else content
        if len(content) < 20:
            content += "，麻烦帮忙确认一下流程"
        gap = intent in GAP_INTENTS
        doc_id = None if gap else random.choice(by_intent[intent])
        n += 1
        ca = datetime(2026, 10, 1) - timedelta(days=random.randint(0, 540),
                                               hours=random.randint(0, 23))
        tickets.append({
            "ticket_id": f"TK{n:05d}",
            "created_at": ca.isoformat(timespec="minutes"),
            "channel": random.choice(["电话", "在线客服", "邮件", "工单门户", "企业微信"]),
            "content": content,
            "intent_label": intent,
            "urgency": random.choices(["高", "中", "低"], weights=[0.18, 0.5, 0.32])[0],
            "status": random.choices(["已解决", "处理中", "已关闭"], weights=[0.72, 0.16, 0.12])[0],
            "handling_minutes": random.randint(4, 180),
            "linked_doc_id": doc_id or "",
        })
    return tickets


# ================================================================ ground truth
def build_ground_truth(docs, corrupt_ids):
    dup_groups, seen = [], set()
    for d in docs:
        if d.get("dup_of"):
            root = d["dup_of"]
            key = tuple(sorted([root, d["doc_id"]]))
            if key not in seen:
                seen.add(key)
                dup_groups.append(list(key))
    # 把三篇组合并
    merged = {}
    for g in dup_groups:
        root = g[0]
        merged.setdefault(root, set()).update(g)
    merged = {k: sorted(v) for k, v in merged.items()}

    return {
        "base_date": BASE_DATE.isoformat(),
        "seed": 42,
        "gap_intents": GAP_INTENTS,
        "corrupt_doc_ids": sorted(corrupt_ids),
        "dup_groups": [sorted(v) for k, v in sorted(merged.items())],
        "n_gap_intents": len(GAP_INTENTS),
        "n_corrupt_docs": len(corrupt_ids),
        "n_dup_groups": len(merged),
        # 防作弊对照集：生成器 4% 分支实际命中的文档（抽样时刻为"自然陈旧"）。
        # 后续埋设步骤可能覆盖其中部分文档的日期或使其同时成为缺陷，
        # 因此本键记录的是"抽样命中数"，实际误报归因见 corrupt_docs.csv 的
        # in_control_sample 与 fp_reason 两列。
        "control_doc_ids": sorted(d["doc_id"] for d in docs if d.get("_control_sampled")),
        "n_control_docs": sum(1 for d in docs if d.get("_control_sampled")),
    }


def main():
    docs, corrupt_ids = gen_docs()
    tickets = gen_tickets(docs)

    doc_fields = ["doc_id", "title", "content", "category", "created_at",
                  "last_modified", "effective_date", "status", "ref_count",
                  "corrupt", "corrupt_reason"]
    with open(os.path.join(HERE, "docs.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=doc_fields)
        w.writeheader()
        for d in docs:
            w.writerow({k: d.get(k, "") for k in doc_fields})

    tk_fields = ["ticket_id", "created_at", "channel", "content", "intent_label",
                 "urgency", "status", "handling_minutes", "linked_doc_id"]
    with open(os.path.join(HERE, "tickets.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=tk_fields)
        w.writeheader()
        w.writerows(tickets)

    gt = build_ground_truth(docs, corrupt_ids)
    n_gap_tickets = sum(1 for t in tickets if t["intent_label"] in GAP_INTENTS)
    gt["gap_ticket_count"] = n_gap_tickets
    gt["gap_ticket_ratio"] = round(n_gap_tickets / len(tickets), 4)
    gt["n_tickets"] = len(tickets)
    gt["n_docs"] = len(docs)
    with open(os.path.join(HERE, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("[gen_data] 生成完成")
    print(f"[gen_data] docs.csv           : {len(docs)} 篇")
    print(f"[gen_data] tickets.csv        : {len(tickets)} 条")
    print(f"[gen_data] 业务域             : {len(set(d['category'] for d in docs))} 个 -> "
          f"{sorted(set(d['category'] for d in docs))}")
    print(f"[gen_data] 工单意图数         : {len(set(t['intent_label'] for t in tickets))} 个")
    print(f"[gen_data] 正文长度(字)        : min={min(len(d['content']) for d in docs)} "
          f"max={max(len(d['content']) for d in docs)} "
          f"avg={sum(len(d['content']) for d in docs) // len(docs)}")
    print(f"[gen_data] 缺口意图           : {GAP_INTENTS}")
    print(f"[gen_data] 缺口工单           : {n_gap_tickets} 条 ({n_gap_tickets / len(tickets):.1%})")
    print(f"[gen_data] 腐化文档(埋)       : {len(corrupt_ids)} 篇")
    print(f"[gen_data] 重复组(埋)         : {len(gt['dup_groups'])} 组")
    for g in gt["dup_groups"][:5]:
        print(f"[gen_data]   dup group: {g}")
    print(f"[gen_data] ground_truth.json 已写出")
    print("=" * 70)


if __name__ == "__main__":
    main()
