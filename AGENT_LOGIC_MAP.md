# AI 智能助理 (Agent) 运转原理：竖向极简版

为了方便您在手机或窄窗口上下滑动查看，我将架构调整为了纯竖向的逻辑流。

---

## 🔝 核心逻辑流 (竖向架构)

```mermaid
graph TD
    User(("👩‍💻 用户 (发出指令)"))
    
    subgraph S1 [第一层：前台接待]
    Mouth("嘴巴 (main.py)<br/>负责听话和回话")
    end
    
    subgraph S2 [第二层：指挥大脑]
    Brain("大脑 (agent.py)<br/>负责分析意图和下令")
    Rules("遵守家规<br/>(不准胡编/微信专用流程)")
    end
    
    subgraph S3 [第三层：执行手脚]
    Hands("手臂 (tools.py)<br/>负责操作电脑办实事")
    H1("🌐 联网搜新闻")
    H2("💬 自动发微信")
    H3("📸 视觉看屏幕")
    H4("🖥️ 操作浏览器")
    end

    %% 流程连接
    User --> Mouth
    Mouth --> Brain
    Brain --> Rules
    Rules --> Hands
    
    Hands --> H1
    Hands --> H2
    Hands --> H3
    Hands --> H4
    
    %% 回馈流程
    H2 -.-> Brain
    Brain -.-> Mouth
    Mouth -.-> User
```

---

## 🔄 极简三步走

1.  **听令**：你在 `main.py` 输入文字，接待员把话传给大脑。
2.  **办事**：`agent.py` 指挥官翻开工具箱 `tools.py`，派派手脚去上网、翻微信、看图。
3.  **结果**：小助手办完事，原路返回告诉你结果。

---

## 📂 文件分工一览

*   **`main.py`**：你的“对讲机”。
*   **`agent.py`**：它的“逻辑核心”。
*   **`tools.py`**：它的“万能工具箱”。
