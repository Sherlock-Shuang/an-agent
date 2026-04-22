import os
import sys
from dotenv import load_dotenv
from agent import SimpleAgent

def main():
    print("欢迎来到属于你的第一个 Agent 终端程序！")
    print("="*40)

    # 加载 .env 环境变量文件
    load_dotenv()
    
    # 检查是否配置了 API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n 错误：未检测到 OPENAI_API_KEY 环境变量。")
        print("请在项目根目录下创建一个 .env 文件进行配置。")
        print("如果你不知道怎么做，请先把 .env.example 复制一份并改名为 .env。")
        sys.exit(1)

    
    # 导入我们自己写的 Agent 类。这里不能放在前面，是因为你想看到没有环境变量时最快的报错提示
    
    
    # 实例化我们的 Agent
    try:
        agent = SimpleAgent()
        # 顺便打印一下使用的是哪个模型
        print(f"[系统提示] 当前使用的模型为: {agent.model}")
        
        # 增加一个温馨提示，防止小白误用不支持工具的模型
        model_lower = agent.model.lower()
        if "vl" in model_lower or "vision" in model_lower:
            print("\n⚠️ 警告：检测到你正在使用视觉(VL/Vision)大模型！")
            print("绝大多数视觉大模型本身是不支持 Function Calling(工具调用) 的。")
            print("如果你强行让它调用工具，API 接口可能会发生混乱、忽略你的请求甚至返回空白内容。")
            print("强烈建议打开 .env 文件，将 MODEL_NAME 修改回文本模型，如 qwen-plus 或 qwen-max。\n")
            
    except Exception as e:
        print(f"\n❌ 初始化 Agent 失败: {e}")
        print("请检查你的 API_KEY 或 BASE_URL 是否填写正确（以及网络是否联通）。")
        sys.exit(1)
        
    print("-" * 40)
    
    # 一个死循环，维持终端的交互式对话
    while True:
        try:
            # 接收用户的在命令行的输入
            user_input = input("\n 你: ")
            
            # 如果用户敲入的指令是这两个词，咱们就退出循环，从而结束程序
            if user_input.strip().lower() in ['quit', 'exit']:
                print("👋 再见！")
                break
            
            # 如果什么都没输入，就跳过这次循环
            if not user_input.strip():
                continue
                
            # 【核心调用】把用户的话交给 Agent 运行，并获取它最终给我们的回答
            reply = agent.run(user_input)
            
            print(f"\n🤖 Agent: {reply}")
            print("-" * 60)
            
        except KeyboardInterrupt:
            # 捕获用户按下 Ctrl+C 的事件
            print("\n\n中断执行，👋 再见！")
            break
        except Exception as e:
            # 捕获在运行时出现的各种奇怪错误（如网络断开、调用超限等）
            print(f"\n[❌ 发生错误]: {e}")

if __name__ == "__main__":
    main()
