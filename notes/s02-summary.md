# s02: Tool Use — 核心工具与 Skill 设计理念总结

> **笔记作者**: Bob (Tester)
> **阅读材料**: `docs/en/s02-tool-use.md` + `agents/s02.py`
> **日期**: 2025-05-09

---

## 一、核心思想：工具即扩展

**一句话总结**: 添加一个新工具 = 添加一个 handler 函数 + 添加一个 schema 条目，循环本身不需要任何改动。

### 为什么要扩展工具集？

| 问题 | 解决方案 |
|------|---------|
| 只有 `bash` 工具，功能单一 | 增加 `read_file` / `write_file` / `edit_file` 等专用工具 |
| `cat` 截断不可预测 | `run_read` 带行数限制 |
| `sed` 对特殊字符会失败 | `run_edit` 用 Python 字符串替换 |
| 每次 bash 调用都是安全风险 | 在工具层强制路径沙箱（`safe_path`） |

---

## 二、核心组件

### 1. 路径安全沙箱 (`safe_path`)

```python
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
```

**设计要点**: 所有文件操作工具都通过 `safe_path` 检查，防止路径穿越攻击。

### 2. 工具分发表 (`TOOL_HANDLERS`)

```python
TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}
```

**设计要点**: 字典映射，一次查找代替 `if/elif` 链式判断。这是"开放-封闭原则"的体现——对扩展开放，对修改封闭。

### 3. 四种核心工具

| 工具 | 函数 | 功能 |
|------|------|------|
| `bash` | `run_bash` | 执行 shell 命令，含危险命令拦截 |
| `read_file` | `run_read` | 读取文件内容，支持行数限制 |
| `write_file` | `run_write` | 写入文件，自动创建父目录 |
| `edit_file` | `run_edit` | 精确文本替换，仅替换第一个匹配项 |

### 4. Agent 循环（与 s01 一致，未改动）

```python
def agent_loop(messages: list):
    while True:
        response = client.messages.create(...)
        messages.append(...)
        if response.stop_reason != "tool_use":
            return
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)  # ← 唯一查找
                output = handler(**block.input)
                ...
```

---

## 三、Skill 设计理念

从 s02 可以总结出 Skill（工具技能）的设计理念：

1. **单一职责** — 每个工具函数只做一件事（读、写、编辑、执行）
2. **防御性编程** — 路径沙箱、危险命令过滤、异常捕获
3. **可组合性** — 工具通过 `TOOL_HANDLERS` 字典注册，可任意增删
4. **循环不变** — 工具的增加不改变 Agent Loop 核心逻辑
5. **错误友好** — 所有异常返回人类可读的错误信息，而非抛异常

---

## 四、从 s01 到 s02 的变化

| 组件 | s01 (之前) | s02 (之后) |
|------|-----------|-----------|
| 工具数量 | 1 (bash only) | 4 (bash, read, write, edit) |
| 调度方式 | 硬编码 bash 调用 | `TOOL_HANDLERS` 字典映射 |
| 路径安全 | 无 | `safe_path()` 沙箱机制 |
| Agent 循环 | 基础版 | 未改动 (保持一致性) |

---

## 五、测试验证

我在 `tests/test_s04.py` 中为 s04 的类似工具函数编写了 23 个单元测试，覆盖了：

- ✅ `safe_path` 路径验证（4 个测试）
- ✅ `run_bash` 命令执行与安全（5 个测试）
- ✅ `run_write` / `run_read` 文件读写（5 个测试）
- ✅ `run_edit` 文本编辑（4 个测试）
- ✅ `TOOL_HANDLERS` 调度分发（5 个测试）

这些测试同样可以复用于验证 s02 的功能正确性。

---

## 六、运行方式

```bash
cd learn-claude-code
python agents/s02_tool_use.py
```

交互式示例：
1. `Read the file requirements.txt`
2. `Create a file called greet.py with a greet(name) function`
3. `Edit greet.py to add a docstring to the function`
4. `Read greet.py to verify the edit worked`
