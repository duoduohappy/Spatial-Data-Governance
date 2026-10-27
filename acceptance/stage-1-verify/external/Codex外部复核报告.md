# GeoAcceptance Stage 1 外部复核报告（Codex）

日期：2026-10-26。结论：当前 Stage 1 暂不通过，整改复验 compare 存在错误完成判定；保留已通过的空间库替换和回归成果，先定向修复，不进入 Stage 2。

## 一、验收独立性与对象

用户交来的《GeoAcceptance-Stage1-独立验收报告.md》由执行方在同一会话内编制，报告已主动说明独立性限制。它不是本聊天 Codex 此前作出的验收结论。本文件是外部复核，单独保存，不覆盖原报告。

在独立复制的源码目录运行；未改原仓库。使用执行方项目 .venv 中的 Python 及已安装依赖，设置 PYTHONDONTWRITEBYTECODE=1。这验证当前依赖环境可运行，不等同于本次重新安装或独立验证锁文件能在新环境安装。未执行 Docker。

## 二、本次已实跑的通过项

- 六包门禁 ALL_OK=true。
- recheck_probes：28/28，通过。
- verify_env：ENV_VERIFY_OK=true，真实库调用完成；有 jsonschema.__version__ 弃用警告，不影响本轮结论。
- 空间专业库替换、原语义回归已有可复现成果。

本次新增探针直接调用 compare_batches，并使用新的临时样例；没有改 expected 迁就当前输出。探针与 JSON 另附。

## 三、S1-EXT-01｜P1：没有有效复验通过证据，也能显示 COMPLETE

位置：geoacceptance/compare.py，compare_batches 的 fails 集合与 overall 聚合。

三个独立反例：
1. blocked → blocked：前后总体均 FAIL，CRS 声明错误根本没改；compare 返回 COMPLETE，counts={}。
2. clean → ambiguous：整改后总体 INDETERMINATE，缺阈值与精度依据；compare 返回 COMPLETE，counts={}。
3. 仅一条过期记录的批次 → 同数据但 R09 状态改 DRAFT：整改后 INDETERMINATE，compare 却标 fixed=1、COMPLETE。

原因：只比较 FAIL finding，且忽略运行和条款覆盖；无 finding 被当成没有问题。数据集级 finding 没有 record_id 时被从台账移除，identity.ok 虽为 false，也没有阻止总体 COMPLETE。

修复要求：
- fixed 必须具有整改后同一适用检查已完整执行且通过的正面证据，不能仅依据“after 没有 FAIL finding”。
- REJECTED、DRAFT、FAILED、BLOCKED、未映射、缺结果、部分覆盖等状态阻断对应问题的关闭。
- 数据集级问题用独立数据集身份追踪（规则身份＋证据域等），不能因无 record_id 消失。
- 总体不能只由 items 的空/非空判断。明确“全部验收通过”与“所选失败台账已处理”的区别，并在报告中完整展示未知/候选范围；当前命名“整改完成”会误导。
- 保留已知 FAIL，不要把任何未知一律覆盖成没有失败。

## 四、S1-EXT-02｜P1：删除有缺陷的实体被直接算作修复

复现：clean 数据的第一条改为过期时间，构成 before 的唯一失败；after 直接删除该实体，其余保持干净。
实际：before FAIL，after PASS；compare fixed=1、overall=COMPLETE。

这不是“同一实体检查已通过”。原文没有批准删除该交付对象；系统缺少该实体的整改后记录。

修复：先核对 before/after 全量实体清单。缺失实体默认 not_comparable 或显式 removed_pending_review；只有有可追溯的批准删除政策与审核记录，才能按该政策结案。新增实体也应单独披露；不能仅比较出现过失败的实体。

## 五、S1-EXT-03｜P2：把 finding 数量误当成实体重复次数

位置：_fail_codes_by_record。

复现：一个唯一 record_id，同时存在非法 category 和过期 source_time 两项缺陷；after 正确修复，两批业务 ID 都唯一。
实际：比较器声称该 ID 重复，not_comparable=2、INDETERMINATE。

原因：Counter 针对 findings 计数。同一实体出现多条 finding 不等于数据内出现多条实体记录。

修复：身份唯一性从全量输入记录计算，分别建立缺失/唯一/重复索引。findings 只是关联该索引的证据；同一记录多个规则或同规则多个问题均不能形成伪重复。重复 ID 即使未产生某类 finding，也要正确识别。

## 六、S1-EXT-04｜P1（已知实现缺口，需补回归）：版本比较不足以证明检查尺子相同

代码审查：_rule_versions 只取 rule.version，不比较规则类型、参数、字段映射、批准来源、依赖、字典、区域和 reference_time。规则被移除的 before 问题也没有专门不可比判定。

当前已实跑的 DRAFT 反例属于“检查资格发生变化却被标修复”，见 EXT-01。对于同版本改参数/字典/区域的路径，本轮尚未另做完整故障注入，不将它描述成已实测。

修复：建立语义指纹，不只检查人工递增的版本号；涵盖实际影响判定的配置与引用制品。尺子不同默认 not_comparable，除非显式采用同一规则重算两批并记录。补同版本改参数、改字典、改区域、改参考时间、规则删除/新增、依赖失效等回归。

## 七、Stage 1 范围尚未闭合

目前 CLI run 调用门禁 main，仍必须与 examples 的 expected 比对。它是回归工具，不是可用于任意交付包的正式 validate 入口。没有 expected 的新包不能按原方案独立验收。

需将“真实检查执行”和“与冻结真值回归比对”分离。正式 validate 不需要 expected；回归工具再显式调用 expected 比对。可以先支持 bundle 目录，不要求此时做 Web 上传或任意复杂格式。

此外，输入上限/UTF-8 防护已有实现，但完整输入格式、逐规则参数约束和任意包实际执行应继续按 Stage 1 门槛补齐。compare 输出应补 Schema 和相同的输入防护。不要将这些视为已经完成整个 Stage 1。

## 八、非阻断事项与现状表述

- 锁文件的 Python 支持范围必须明确。3.11 使用另一套不锁版本依赖运行成功，不代表该锁文件支持 3.11；不能把代码兼容性与安装可复现性混为一谈。
- Docker 未执行可作为环境限制保留，不阻止本轮先修 compare。
- README 仍同时出现“5 组”与“六组”，且首段“等待独立验收”与后段“已完成独立复验”容易误读；同步为执行方自验与外部验收各自状态即可。
- 不需再追加大量原因码或复杂架构，优先完成最小可用且诚实的 compare。

## 九、下一轮最小验收包

1. 固定修复 commit；保留本轮外部复核与原自验报告，分别标明来源。
2. 本轮五个实际反例全部进入回归：数据集失败未修、缺证据、规则未批准、删实体、唯一实体多 finding。
3. 增加 EXT-04 的尺子变化测试，证明规则变更不能制造修复。
4. compare 的记录/规则/数据集资格和总体判定表；缺证据、不适用、不完整必须可见。
5. 六包、28 项回归继续通过；新增可用正式 validate 入口，无 expected 也能检查新包。
6. 提供原始 JSON、实际命令和未解决问题。不以截图或全绿计数替代正确性证据。

结论：不撤销已验证的库替换成果；当前阻断点集中在 compare 的关闭证据与身份。修好后重验 Stage 1，不扩展到 AI、多 Agent、网关或 Web。

## 十、补充：执行方 13 项探针的外部重跑

本次源码目录对应当前归档 HEAD b183849（功能验收对象 e4e849a，后续 e7a2daa/b183849 为报告归档）。执行方提供的 13 项探针也已重跑：第一次因本会话沙箱临时目录不可写，6 项报 PermissionError，不将环境限制记作产品缺陷；将 TEMP/TMP 显式设到工作区可写目录后，13/13 通过。该结果仍与本轮新增五项 compare 反例同时成立，说明原探针覆盖不足以排除这些错误，而非原 13 项运行记录必然不实。
