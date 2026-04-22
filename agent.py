import os
import json
from openai import OpenAI
from tools import TOOLS_DEFINITION, TOOLS_MAP

class SimpleAgent:
    def __init__(self):
        # 1. 初始化大模型客户端
        # 如果你不手动传接口地址和密钥，它会自动读取环境变量中的 OPENAI_API_KEY / OPENAI_BASE_URL
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        
        # 获取模型名称，如果没有设置则默认使用 qwen-plus
        self.model = os.getenv("MODEL_NAME", "qwen-plus")
        
        # 2. 初始化记忆（对局的历史 / System Prompt）
        # 大模型本质是“补全对话”，我们要告诉它：它的身份是什么
        self.messages = [
            {
                "role": "system", 
                "content": (
                    "你是一个强大的 AI 助手 (Agent)，专注于帮助用户操作电脑和处理信息。\n"
                    "你有能力且必须优先使用各种工具来辅助用户。遇到任何需要搜索外部信息、查阅新闻、或者用户让你操作文件、操作微信时，请**绝对不要**靠幻觉编造，必须严格调用对应的工具！对话内容要全面，不要遗漏任何细节，直到完全满足客户需求为止。\n\n"
                    "【微信/QQ专属规则 - 极其重要】\n"
                    "不论用户让你怎样操作微信或QQ，你**只能**使用以下四个专用工具，**绝对禁止**使用 `take_screenshot` 和 `click_screen` 去瞎点聊天软件界面：\n"
                    "1. 只要涉及到「看微信」、「读消息」，必须且只能调用 `read_wechat_messages` 工具！\n"
                    "2. 只要涉及到「回复微信」、「发微信」，必须且只能调用 `send_wechat_message` 工具！\n"
                    "3. 只要涉及到「看QQ」、「读QQ消息」，必须且只能调用 `read_qq_messages` 工具！\n"
                    "4. 只要涉及到「回复QQ」、「发QQ」，必须且只能调用 `send_qq_message` 工具！\n"
                    "5. 如果要在回复前先了解上下文，你的标准流程是：先调用上面的 read 工具，再调用 send 工具发出去。不要做任何多余的截屏点击动作！\n"
                    "6. 任何工具报错无法聚焦或权限不足，请直接把报错返回给用户，严禁陷入重试死循环。"
                )
            }
        ]

    def run(self, user_input: str, max_iterations: int = 15) -> str:
        """
        核心的 Agent 运行逻辑（也叫做 ReAct 循环，或者是 Tool Calling 循环）
        """
        # 第一步：把用户输入的话追加到"短期记忆（历史）"中
        self.messages.append({"role": "user", "content": user_input})
        
        iterations = 0
        # 开始一个循环：只要模型不停地提出“我想使用工具”，我们就跑工具，然后把结果塞给它。直到它说“我回答完了”
        while iterations < max_iterations:
            iterations += 1
            print(f"\n[🧠 Agent 正在思考中... (轮次: {iterations}/{max_iterations})]")
            
            # 第三步：把整个对话历史发给大模型，并且带上说明书（TOOLS_DEFINITION）
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS_DEFINITION,
                    tool_choice="auto"  # "auto" 意味着让大模型自己决定是调用工具，还是普通聊天
                )
            except Exception as e:
                return f"[API 调用失败] 可能由于网络或参数错误: {str(e)}"
            
            # 提取大模型的回复（可能包含工具调用，也可能就是一段回答文字）
            response_message = response.choices[0].message
            
            # 兼容性修复：部分非 OpenAI 原生的 API 处理 Pydantic 对象可能存在 bug。
            # 这里安全地将其转化为普通的 Python 字典，并去除为空(None)的字段
            msg_dict = response_message.model_dump(exclude_none=True)
            self.messages.append(msg_dict)
            
            # 第四步：判断模型是否决定调用工具
            if response_message.tool_calls:
                # 遍历模型想要调用的每一个工具 (有些模型支持一次并行调用多个工具)
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    # 参数是 json 格式的字符串，我们需要解析成 Python 的字典对象
                    function_args_str = tool_call.function.arguments
                    
                    try:
                        function_args = json.loads(function_args_str)
                    except json.JSONDecodeError:
                        function_args = {}
                    
                    # 第五步：执行本地的具体函数
                    function_to_call = TOOLS_MAP.get(function_name)
                    if function_to_call:
                        # 相当于执行 search_web(query="xxx")
                        function_response = function_to_call(**function_args)
                        
                        # 第六步：把工具返回给我们的结果(Observation)，告诉大模型
                        # role 必须填 tool，以此让模型知道这是工具的结果
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": str(function_response),
                        })
                    else:
                        print(f"未能找到工具: {function_name}")
                        
                # 循环的 continue！工具执行完了，带着执行结果，再跑到 while True 顶部去重新向大模型发起对话请求！
                # 让大模型结合工具结果继续思考：任务解决了吗？还需要其他工具吗？还是直接告诉用户结果？
                continue 
                
            else:
                # 容错处理：如果 Qwen 等模型因为触发了“敏感词审查”或者其他未知安全机制，
                # 导致它强行切断并且返回了一个空的 content 时，我们需要提醒用户重试。
                if not response_message.content or response_message.content.strip() == "":
                    return "（由于大模型的内部安全机制或网络波动，本次返回了空白内容。这通常和搜索词敏感或长上下文风控有关，请换个问题试试吧！）"

                # 正常情况：大模型没有请求工具，并且正常返回了文本内容
                return response_message.content

        return f"（系统强制中断）：我已经连续思考和调用工具 {max_iterations} 次了。为了防止陷入死循环或过度消耗 API Token，本次任务被强制暂停。请您检查我的工作过程，或者更换更简单的指令。"
