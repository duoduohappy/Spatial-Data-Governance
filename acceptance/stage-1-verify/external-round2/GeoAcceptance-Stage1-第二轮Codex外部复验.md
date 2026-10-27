# GeoAcceptance Stage 1 第二轮外部复验（Codex）

日期：2026-10-26。
结论：上一轮整改主要路径通过，但 Stage 1 整体仍暂不通过。剩余两项定向修复，不进入 Stage 2；不要求重做已验证成果。

## 1. 验收对象与实测

功能提交 f593630；当前归档 HEAD a2b5797。读取执行方整改说明、代码与 Schema，在独立复制源码目录运行；未修改原仓库。复用项目 .venv 的解释器与依赖，不声称本次完成全新环境锁文件安装。未跑 Docker。

实际结果：
- 六包门禁 ALL_OK=true。
- recheck_probes 30/30。
- compare_probes 18/18。
- 验收方上轮原脚本五例重跑：
  1 blocked→blocked：LEDGER_OPEN，still_open=1。
  2 clean→ambiguous：LEDGER_CLOSED_NOT_ACCEPTED，未放行。
  3 删除有缺陷实体：LEDGER_INDETERMINATE，removed_pending_review=1。
  4 R09 改 DRAFT：LEDGER_INDETERMINATE，unresolved_unknown=1。
  5 唯一实体多个 finding 修复：LEDGER_CLOSED_ACCEPTED，closed=2，不再误判 ID 重复。

认可上述修复，也认可正式 validate 与 expected 回归入口分离。新增输出 Schema 不能替代输入参数校验，见下。

## 2. S1-R2-01｜P1：逐规则参数 Schema 未接入正式执行入口

位置：tools/input_models.py 的 Rule.parameters 为 Dict[str, Any]；validate_bundle 调 collect_config_rejections，但没有完整执行 schemas/rule.schema.json 的逐规则参数约束。

独立反例：
1 从 clean 复制新包。
2 将 R01.parameters.fields 设为 []。
3 从 poi.csv 表头与每条记录实际删除 name 列。
4 调用正式 validate_bundle。

实际：aggregate_verdict=PASS、config_rejections=[]。
预期：至少拒绝非法规则配置，结论 INDETERMINATE，executed=false；不能称必需字段检查已通过。

这不是新增业务范围：rule.schema.json 中 required_field_present 分支已经写 fields.minItems=1。现有单独 Schema 检查与实际执行入口脱节，属于已声明契约未执行。整改说明把“逐规则参数约束”列为以后再做，与 Stage 1 的入口校验门槛不符。

最小修复：
- 在所有正式执行入口统一执行十类规则参数 Schema 或等价 Pydantic 判别联合，不能只校验 Dict 类型。
- 缺参数、空必需数组、错误类型、非法枚举、未知参数、未知 rule_type 都受控拒绝；不忽略参数后继续默认执行。
- validate、compare、regress 复用同一入口校验，不维护三套宽严不同的规则。
- 至少为十类规则各加一个入口级非法参数用例；保留有效输入正向对照。
- 拒绝后结构化报告保留应检查的条款数量；不要把拒绝执行说成项目没有条款。

## 3. S1-R2-02｜P1：删除“原本干净”的交付实体仍可整体放行

位置：geoacceptance/compare.py。实体差异从全量记录计算，但 removed_pending_review 只在 finding 台账循环中生成。

独立反例：clean→clean 副本，after 只删除 SD-0001，其余保持不变。
实际：scope.entities_removed_after=[SD-0001]，但 overall=LEDGER_CLOSED_ACCEPTED；不产生阻断项。
预期：在尚无批准删除通道的当前政策下，缺失交付实体应显式待审核，不能自动判“全部验收通过”。

原因：目前只有“带失败 finding 的记录被删除”才阻断；无缺陷记录不进台账，其消失只披露、不阻断。这个差别没有批准的业务依据，也不符合本轮说明“一律 removed_pending_review”的表述。

最小修复：
- 在全量 before/after 实体清单差集上生成 removed_pending_review，而非只依赖 findings；去重避免多条规则重复计实体。
- 删除已故障实体和干净实体都待审核；新增实体保持明确披露。
- 当前先不做批准删除通道，继续保守阻断。若要允许某类删除，必须先显式定义政策与可追溯批准，不能用“原本没问题”自动授权。
- 补干净实体删除、故障实体删除、仅新增、无变化、行顺序变化五组测试。

## 4. 范围与阶段结论

本轮没有撤销库替换、旧反例修复和 validate 分离成果。问题集中在已有门槛，不需要再追加架构、原因码体系、置信度路由或 Web。

Docker 环境限制、Python 3.11 锁文件、重批准触发不可比等已知事项可继续登记。本轮不因这些非当前阻断问题要求额外扩建。

Stage 1 下一轮交付最小要求：
1 固定修复 commit；
2 两个外部新增反例变成正式回归；
3 十类规则入口参数反例与有效输入对照；
4 六包、30 项、18 项及新增回归结果；
5 正式 validate 无 expected、compare 两批同等校验的原始 JSON 与命令；
6 更新现状说明，不能将未接入的参数验证写成可延期而同时申请整个 Stage 1 通过。

修复后再做短轮复验，通过后即可进入 Stage 2 的条款提取与人工确认；目前不启动模型、多 Agent、网关或 Web。
