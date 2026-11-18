# Vector Result Audit：向量检索结果与回归验收

检查真实检索结果里的重复／未知ID、过滤外数据、距离编码错误、缺失分数、排序错误，以及两次运行的逐查询退化。核心零第三方运行时依赖，不要API key，不下载模型，报告全部在本地。

## 先跑起来

Python3.10+，源码目录执行：

```sh
python -m pip install .
vector-audit demo --out audit-demo
vector-audit check audit-demo/broken.json --json findings.json --html findings.html
```

打开HTML。故意错误样例返回1是预期结果。退出0=声明检查通过；1=发现合同违规／预算不达标／回归；2=输入不可比、预算超限或输出错误。

## v0.2新增的实际用途

- **真实库入口**：Faiss和Qdrant的结果转换，不猜ID、不偷偷去重或重排。Faiss平方L2与Qdrant普通L2明确区分，-1占位保留原位置。
- **两次运行比较**：`vector-audit compare before.json after.json --html regression.html`。先证明语料、查询、资格、metric/k和策略相同，再比较；不静默取交集，不让平均提升掩盖单查询退化。
- **显式验收意图**：`require_scores`要求非占位行有分数；`require_sorted`检查参考排名顺序与尾部padding，默认均false以兼容旧输入。
- **直接定位证据**：报告列出缺失的严格更近邻居ID、完整数值、查询／行锚点和score已查／缺失数量。
- **数值与I/O修复**：cosine分数不再经1−距离反算丢失微小值；缩放归一化支持次正规数；计算预算在语料复制前拒绝；stdout追加到输入的别名被拦截，断管道返回2不冒充通过。

三个邻居距离0、1、1，要top2却返回后两个，召回是0.5而非1；另一种合法边界并列项不能被误报成缺失。

## 运行真实库对照

独立Python3.12环境中：

```sh
python -m pip install -r integrations/requirements.txt
python -m unittest discover -s integrations -v
python -m examples.engine_capture --out engine-demo
```

示例实际运行Faiss CPU IndexFlat及Qdrant-client内存模式，生成可比的baseline/candidate和报告。错误是明确标注的人工导出／应用层错误注入；不伪装上游数据库漏洞。**Qdrant本地模式不等于服务器验证，IndexFlat不等于ANN性能验证。** 详见[集成说明](docs/integrations.md)。

## 不夸大的边界

资格名单和快照由调用方提供，工具不证明ACL实现、最新性、完整性、语义相关性或RAG答案质量。空资格集recall是N/A；未设置min_recall的PASS不保证召回质量；score缺失默认仍是未核验。

v0.2报告schema为2，输入schema仍为1。cosine按负的直接相似度排名，display distance仍是1−similarity；两者不混用，score容差不合并名次。不是实数精确证明。

CLI输入默认32MiB，n×q×d预算500万，累计结果1万行，总查询＋结果＋参考证据2万行；compare两侧分别限额，不是全进程RSS保证。输出文件／stdout都不能指向输入，但shell的 `>` 会在程序启动前截断文件，工具无法倒退恢复。详细安全边界见[英文README](README.md)和[合同](docs/contract.md)。

核心及集成测试、错误注入和实际制品均须真实验证；发布后的远程CI以真实回执为准。没有宣称世界第一、算法首创、已有外部用户或固定Star数量。MIT许可，AI辅助工程实现。
