# 制药企业产品成本智能分析系统（计算内核 · 阶段 1）

> 2026 年第二届重庆市 AI 大模型创新应用大赛
> 赛题：《基于 RAG 与大模型的制药企业产品成本智能分析报告系统》

## 本目录内容

阶段 1 交付物——数据与计算层（单一事实源）：

- `app/core/datastore.py` — 统一数据访问层（定位器，月份统一 `YYYY-MM`）
- `app/core/calc.py` — 计算服务（环比/同比/预算偏差、三因素分解、回归固定变动、价量对数分解、隐含单耗双检验、对标差异、阈值校准、专项核验）
- `app/core/assertions.py` — 恒等式断言库（出题方声明的恒等式 + 七轮评审验证关系）
- `golden_numbers.json` — 金丝雀基准集（七轮评审独立复算的全部锚点数字）
- `tests/` — pytest 测试（金丝雀 + 断言库）
- `scripts/run_checks.py` — 免 pytest 一键检查

## 运行

```bash
# 数据路径（默认指向赛题数据包，可用环境变量覆盖）
# 可选: set COST_DATA_DIR=你的数据包路径

# 方式一：一键检查
python scripts/run_checks.py

# 方式二：pytest
pytest -q
```

**验收标准：全部 PASS。任何一条失败 = 计算层被破坏，禁止进入下一阶段。**

## 铁律（v7 终版）

1. 一切报告数字只允许来自 `app/core/calc.py`；
2. 价量分解只输出变动贡献，绝对单耗不可校准（理论 vs 实际两套口径）；
3. 同一比值的多个量必须取自同一时间窗口（窗口对齐硬规则）；
4. 固定/变动分解统一最小二乘回归并标注 R²，高低点法仅作敏感性参照。

## 合规性（对照赛题条款）

- **5.1.2 文档格式**：支持 **PDF（pypdf）/ Word（python-docx，段落+表格）/ TXT（多编码）**，
  统一走"NFKC → 分节 → 滑窗 → 元数据"管线（`app/rag/parse.py`，验收见 `tests/test_formats.py`）；
- **5.1.2 三类知识**：产品（配方）/行业（行情+基准+GMP）/企业（工艺+设备台账）三类均有分块与索引，
  元数据带明确 `type` 标记；
- **5.1.2 混合检索 + 来源标注**：BM25+向量双通道 RRF 融合；每条结果带文件名/页码/章节/版本；
- **6.1 向量数据库**：ChromaDB（持久化，内容签名集合名），numpy 无网降级，双后端一致性测试锁定；
- **6.1 语义检索（两级方案）**：默认自动选择——本地语义模型（中文句向量，离线可用，
  满足"语义检索"本义，同义改写查询命中）；**未安装/无网时自动降级 IDF 哈希嵌入**
  （确定性，演示机兜底，答辩口径如实说明）。
  模型获取（国内走 ModelScope，无需科学上网）：
  ```bash
  pip install modelscope sentence-transformers
  python -c "from modelscope import snapshot_download; print(snapshot_download('iic/nlp_gte_sentence-embedding_chinese-small'))"
  # 把打印出的本地路径设给环境变量（系统将自动探测该路径，或显式设置）：
  set RAG_EMBED_MODEL=D:\path\to\nlp_gte_sentence-embedding_chinese-small
  ```
  `RAG_EMBED_FORCE=hash` 强制兜底；系统自动探测 ModelScope 缓存路径与 HF 默认模型名；
- **6.2 知识图谱增强 RAG**：networkx 图谱真实融入检索链路（实体锚定→多跳路径→证据通道）；
  Neo4j 为预留适配层；
- **6.1 框架**：LangChain 集成计划于阶段 3（HybridRetriever 包装为 BaseRetriever）。

## RAG 权重与边界保证（阶段 2 评审修复记录）

**混合检索权重经验证**：BM25 0.3 / 向量 0.7（README 建议值）与 0.5/0.5、0.2/0.8
做了消融对比——确定性嵌入下三种权重在 6 条归因查询上命中率一致（6/6），
查询感知类型权重层起主导作用；按 README 建议保留 0.3/0.7（`tests/test_ablation.py`）。

**边界保证（`tests/test_boundary.py`）**：
- 空查询守卫：0 结果、不触发图谱锚定、<2s 返回；
- 繁体查询：领域词繁→简映射，命中与简体一致；
- 纯符号/超长查询：不崩溃、快速返回；
- 双后端一致性：chroma 与 numpy 降级后端 top-5 逐位一致；
- 哈希碰撞率监控：词表→桶碰撞率 < 25% 断言（IDF 加权 + dim 8192，当前 ≈17%）。

## 图谱（阶段 2）

- 实体表人工核对（`app/rag/entities.py`）：BOM 用折算口径、29 台设备、维修事件、
  六条场景事件（含判定等级）；行情事件层 13 药材×6 月带月份属性；
- 多跳路径覆盖：产品→药材→行情事件、产品→设备→维修事件、车间→设备、
  六条场景事件 E1-E6 全部可达（`tests/test_rag.py`）；
- 存储：networkx 为主；Neo4j 为预留适配层（接口已留，待服务器就绪后提供 Cypher 回放脚本）。

## 保密

赛题数据仅限本次大赛使用。本仓库绝不包含任何 CSV/PDF 原始数据（已 .gitignore）。
