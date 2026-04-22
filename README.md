# 🤖 OmniAgent: 你的本地自主智能助理
> **轻量级、高性能、可扩展的本地 AI Agent 框架，助你自动化真实世界的复杂任务。**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Framework](https://img.shields.io/badge/framework-OpenAI--compatible-orange.svg)](https://openai.com/)

**OmniAgent** 不仅仅是一个聊天框。它基于 **ReAct (Reasoning + Acting)** 架构，赋予大模型“大脑”指令，通过“手脚”工具集直接操作电脑，完成从联网搜索到社交软件自动化的端到端任务。

---

## ✨ 核心能力

| 🧠 决策大脑 | 👁️ 视觉感知 | 🛠️ 自动化执行 | 📱 社交深度集成 |
| :--- | :--- | :--- | :--- |
| **ReAct 循环**: 纯 Python 实现的逻辑推理环，决策过程完全透明。 | **VLM 视觉**: 调用 `qwen-vl` 模型实时“看见”并理解你的屏幕内容。 | **RPA 操控**: 原生支持屏幕点击、键盘输入和桌面窗口管理。 | **微信/QQ 自动化**: 针对社交应用定制的免点击、高可靠性消息处理流。 |
| **全网搜索**: 实时并发的 DuckDuckGo 搜索，告别知识陈旧。 | **动态快照**: 自动捕获当前上下文，彻底消除模型幻觉。 | **网页自动化**: 集成 Selenium 实现复杂的表单填充与网页交互。 | **安全准则**: 严苛的内置规则，防止 Agent 在社交软件中陷入封号风险。 |

---

## 🚀 快速上手

### 1. 环境准备
克隆项目并安装核心依赖：
```bash
pip install -r requirements.txt
```

### 2. 环境配置
复制 `.env.example` 并填入你的 API 密钥：
```bash
cp .env.example .env
```
配置 `.env` 文件：
```env
# 建议使用阿里云百炼，兼容 OpenAI 格式
OPENAI_API_KEY="sk-你的密钥"
OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME="qwen-plus"
```

### 3. 开启进化
在终端启动交互式 Agent：
```bash
python main.py
```

---

## 🏗️ 架构概览

OmniAgent 采用三层模块化设计，兼顾性能与扩展性：

1. **`main.py` (交互层)**: 
   - 终端 UI 管理。
   - 会话生命周期控制与错误捕获。
   
2. **`agent.py` (指挥层)**: 
   - **核心逻辑大脑**。
   - 负责任务拆解、工具选择以及“自我纠错”。
   - 维护短期记忆与系统指令。

3. **`tools.py` (执行层)**: 
   - **万能工具箱**。
     - **Web 模块**: 搜索、抓取、表单填充。
     - **视觉模块**: 屏幕分析、图片解读。
     - **OS 模块**: 文件读写、搜索、应用聚焦。
     - **社交模块**: 微信/QQ 专属 RPA 逻辑。

---

## 🛠️ 高级工具集

| 工具名称 | 功能描述 |
| :--- | :--- |
| `search_web` | 全网实时搜索，获取最新资讯。 |
| `analyze_image` | 唤醒视觉子模型，对图片进行深度解读。 |
| `read_wechat_messages` | 通过 VLM 视觉读取微信聊天记录并总结。 |
| `auto_fill_web_form` | Selenium 驱动的网页自动化填充。 |
| `take_screenshot` | Agent 的“眼睛”——捕获屏幕并通过 AI 分析。 |

---

## 📜 协作准则

- **文档优先**: 任何工具或脚本的变更必须同步更新此 README。
- **原子化工具**: 新增功能应作为独立函数在 `tools.py` 中实现，并注册至 `TOOLS_DEFINITION`。
- **安全边界**: 严禁让 Agent 使用原始点击操作社交软件界面，必须通过专用 RPA 函数以确保安全。

---

## 📄 开源协议
本项目采用 MIT 协议开源。
