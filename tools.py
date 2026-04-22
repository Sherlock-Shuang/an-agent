import os
import time
import json
import subprocess
from datetime import datetime
from duckduckgo_search import DDGS
import docx
import requests
from bs4 import BeautifulSoup
import base64
from openai import OpenAI
import mimetypes


# ====== 内部辅助函数 ======

def _ensure_wechat_focused(max_retries: int = 3) -> dict:
    """
    尝试激活微信窗口并置于前台。
    为了兼容性，使用最底层的 open -a 命令，而不是依赖容易被拦截的 AppleScript System Events。
    返回 {"success": True/False, "message": "..."}。
    """
    for attempt in range(1, max_retries + 1):
        try:
            # 优先尝试英文名
            try:
                subprocess.run(["open", "-a", "WeChat"], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # 备用尝试中文名
                subprocess.run(["open", "-a", "微信"], check=True, capture_output=True)
                
            # 给微信一点时间完成窗口切换动画
            time.sleep(0.3)
            return {"success": True, "message": f"通过 open 命令尝试唤醒微信完成 (尝试 {attempt}/{max_retries})"}
        except Exception as e:
            print(f"[⚠️ 重试 {attempt}/{max_retries}] 唤醒微信失败: {e}")
            time.sleep(0.3)

    return {
        "success": False,
        "message": f"经过 {max_retries} 次尝试仍无法唤醒微信应用程序。"
                   f"请确微信已经安装并登录。"
    }

def _ensure_qq_focused(max_retries: int = 3) -> dict:
    """
    尝试激活 QQ 窗口并置于前台。
    使用 open -a QQ 命令。
    返回 {"success": True/False, "message": "..."}。
    """
    for attempt in range(1, max_retries + 1):
        try:
            subprocess.run(["open", "-a", "QQ"], check=True, capture_output=True)
            time.sleep(0.3)
            return {"success": True, "message": f"通过 open 命令尝试唤醒 QQ 完成 (尝试 {attempt}/{max_retries})"}
        except Exception as e:
            print(f"[⚠️ 重试 {attempt}/{max_retries}] 唤醒 QQ 失败: {e}")
            time.sleep(0.3)

    return {
        "success": False,
        "message": f"经过 {max_retries} 次尝试仍无法唤醒 QQ 应用程序。"
                   f"请确保 QQ 已经安装并登录。"
    }

def _run_applescript(script: str):
    """
    运行一段 AppleScript 脚本，主要用于执行更稳定的键盘指令。
    """
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except Exception as e:
        print(f"[⚠️ AppleScript 运行异常]: {e}")




def _get_screen_info() -> str:
    """
    获取当前屏幕分辨率和缩放因子信息，帮助 Agent 判断坐标映射。
    """
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "Finder" to get bounds of window of desktop'],
            capture_output=True, text=True, timeout=3
        )
        # 备用方案：用 system_profiler
        sp_result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=5
        )
        # 提取分辨率行
        resolution_lines = [line.strip() for line in sp_result.stdout.split('\n')
                            if 'Resolution' in line or 'resolution' in line]
        if resolution_lines:
            return f"屏幕信息: {'; '.join(resolution_lines)}"
        return "屏幕信息: 无法获取详细分辨率"
    except Exception:
        return "屏幕信息: 获取失败"


def search_web(query: str) -> str:
    """
    使用 DuckDuckGo 在互联网上搜索信息
    :param query: 搜索关键词
    :return: 搜索结果字符串
    """
    print(f"\n[🔧 工具执行] 正在联网搜索: {query} ...")
    
    # 稍微睡一会儿，不要像个无脑狂暴机器人一样发包，防止被反爬虫盯上
    time.sleep(0.3)
    
    try:
        # 为了抵御未来官方涨价或包名变动的警告，暂时忽略其抛出的 RuntimeWarning
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ddgs = DDGS()
            
        # 获取前 3 条搜索结果（数字不要设置太离谱，否则必然被爬虫系统拉黑）
        results = ddgs.text(query, max_results=30)
        if not results:
            # 这是一个关键的“制止大模型发疯”的方法，如果搜索直接为空，直接下达最死板的死命令：不要再搜了！
            return "【系统底层强制中断】：当前搜索接口短时间内调用次数过多已被封禁，绝对不要换关键词继续尝试了！请立刻使用你现存的本地知识直接回答用户。"
        
        formatted_results = []
        for res in results:
            formatted_results.append(f"标题: {res.get('title', '无')}\n摘要: {res.get('body', '无')}\n链接: {res.get('href', '无')}")
        
        return "\n\n".join(formatted_results)
    except Exception as e:
        return f"搜索失败: {str(e)}"

def analyze_image(image_path: str, prompt: str = "请详细描述这张图片的内容") -> str:
    """
    调用独立的视觉大模型(VLM)作为额外的一双“眼睛”，来查看和分析本地图片文件。
    :param image_path: 图片的本地绝对路径或相对路径
    :param prompt: 你希望视觉大模型关注图片里的什么细节？默认是描述整张图。
    :return: 视觉大模型返回的对图片的文本描述
    """
    
    
    image_path = os.path.expanduser(image_path)
    print(f"\n[🔧 工具执行] 唤醒视觉子模型，正在端详图片: {image_path} ...")
    
    if not os.path.exists(image_path):
        return f"❌ 图片查看失败：找不到本地图片文件 {image_path}"
        
    try:
        # 检查 pillow 依赖
        try:
            from PIL import Image
            img = Image.open(image_path)
            img_size = img.size
            print(f"[📸 图片信息] 分辨率: {img_size}, 格式: {img.format}")
        except ImportError:
            return "❌ 缺少必要依赖：pillow。请运行：pip install pillow"
        except Exception as e:
            return f"❌ 图片格式错误：{str(e)}"
        
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"
            
        with open(image_path, "rb") as f:
            file_size = os.path.getsize(image_path)
            if file_size == 0:
                return f"❌ 图片查看失败：图片文件为空 {image_path}"
            if file_size > 10 * 1024 * 1024:  # 10MB
                return f"❌ 图片文件过大 ({file_size / 1024 / 1024:.1f}MB)，请使用较小的图片"
            base64_image = base64.b64encode(f.read()).decode('utf-8')
            print(f"[📦 编码完成] Base64 长度: {len(base64_image)} 字符")
            
        # 💡 这里是非常关键的套娃调用：在这个普通的方法里，我们再新建一个专看图的 OpenAI Client
        vision_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        )
        
        # 从环境变量读取视觉模型名称，默认为阿里云最强的多模态模型
        vision_model = os.getenv("VISION_MODEL_NAME", "qwen-vl-plus-latest")
        print(f"[🤖 使用模型] {vision_model}")
        
        # 尝试调用视觉模型（包括备选方案）
        models_to_try = [vision_model, "qwen-vl-plus-latest", "qwen-vl-max-latest"]
        
        for attempt_model in models_to_try:
            try:
                print(f"[🔄 尝试模型] {attempt_model}")
                response = vision_client.chat.completions.create(
                    model=attempt_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    timeout=30
                )
                print(f"[✅ 模型成功] {attempt_model}")
                return f"看完图片啦！视觉大脑的观察报告如下：\n{response.choices[0].message.content}"
            except Exception as model_error:
                print(f"[⚠️ 模型 {attempt_model} 失败] {str(model_error)[:100]}")
                last_error = str(model_error)
                continue
        
        # 所有模型都失败了
        return f"❌ 所有视觉模型均失败:\n{last_error}\n\n💡 排查清单：\n1. 检查 API Key 是否有效\n2. 测试网络连接：curl https://dashscope.aliyuncs.com\n3. 确认模型名称正确\n4. 检查图片文件是否正常（pip install pillow 后可预览）\n5. 尝试 VISION_MODEL_NAME=qwen-vl-max-latest"
        
    except Exception as e:
        error_msg = str(e)
        print(f"[❌ 视觉模型错误] {error_msg}")
        import traceback
        traceback.print_exc()
        return f"❌ 视觉子模型执行失败:\n{error_msg}\n\n💡 建议排查：\n1. 检查 VISION_MODEL_NAME 是否正确（当前: {os.getenv('VISION_MODEL_NAME', 'qwen-vl-plus-latest')}）\n2. 运行 pip install -r requirements.txt 重新安装依赖\n3. 检查网络连接和 API Key 有效性"

def take_screenshot() -> str:
    """
    对当前屏幕进行截屏，保存为临时图片，并自动调用视觉子模型进行分析。
    用于当你需要"看一眼"屏幕上当前显示的内容时，尤其是查看微信的聊天列表、并观察微信界面上正在发生什么事。
    :return: 视觉大模型返回的对屏幕图片的详细描述，以及图片保存的路径
    """
    try:
        import pyautogui
    except ImportError:
        return "截屏失败：请先 pip install pyautogui"
    
    # 生成一个以当前时间为即时命名的截屏文件名，保存在临时目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = f"/tmp/agent_screenshot_{timestamp}.png"
    
    print(f"\n[📸 截屏] 正在拍摄当前屏幕快照...")
    try:
        # 检查屏幕是否可访问
        print(f"[📸 检查] 尝试获取屏幕分辨率...")
        try:
            screen_size = pyautogui.size()
            print(f"[📸 屏幕信息] 分辨率: {screen_size}")
            if screen_size[0] == 0 or screen_size[1] == 0:
                return f"❌ 截屏失败：屏幕尺寸无效 {screen_size}。可能原因：\n1. 屏幕被断开连接\n2. macOS 屏幕录制权限不足\n3. 显示器进入休眠\n\n💡 解决方案：\n- 检查系统偏好设置 → 隐私与安全 → 屏幕录制\n- 确认终端有屏幕录制权限"
        except Exception as size_error:
            print(f"[⚠️ 屏幕尺寸获取失败] {str(size_error)}")
        
        # 执行截屏
        print(f"[📸 截屏] 调用 pyautogui.screenshot()...")
        screenshot = pyautogui.screenshot()
        
        # 验证截屏是否有效
        if screenshot is None:
            return f"❌ 截屏失败：pyautogui.screenshot() 返回 None\n\n💡 可能原因：\n1. 屏幕被锁定\n2. macOS 屏幕录制权限不足\n3. 显示器断开连接"
        
        print(f"[📸 验证] 图片尺寸: {screenshot.size}, 模式: {screenshot.mode}")
        
        # 保存截屏
        print(f"[📸 保存] 正在保存到 {screenshot_path}...")
        screenshot.save(screenshot_path)
        
        # 验证文件是否成功生成
        if not os.path.exists(screenshot_path):
            return f"❌ 截屏保存失败：文件未生成 {screenshot_path}"
        
        file_size = os.path.getsize(screenshot_path)
        if file_size == 0:
            return f"❌ 截屏保存失败：文件为空 {screenshot_path}"
        
        print(f"[📸 成功] 截屏已保存 ({file_size / 1024:.1f}KB)，正在调用视觉子模型分析...")
        
        # 获取屏幕分辨率信息
        screen_info = _get_screen_info()
        
        # 重点！截屏完毕后，自动把图片喂给视觉大模型"看"
        vision_result = analyze_image(
            screenshot_path,
            "这是一张电脑屏幕截图。请极其详细地描述截图中能看到的所有界面元素、文字内容、聊天消息、应用窗口以及它们在屏幕上的大致位置。"
            "如果是微信界面，请仔细列出左侧的联系人列表和对应的最新消息预览，以及右侧聊天窗口的具体消息内容。"
            "如果是QQ界面，也请仔细描述聊天内容。"
            "如果能看到消息的发送者名字和时间，也请一并报告。"
        )
        
        return f"截屏已保存至: {screenshot_path}\n{screen_info}\n\n{vision_result}"
    except Exception as e:
        error_msg = str(e)
        print(f"[❌ 截屏错误] {error_msg}")
        import traceback
        traceback.print_exc()
        return f"❌ 截屏失败:\n{error_msg}\n\n💡 排查步骤：\n1. 检查 macOS 系统偏好设置 → 隐私与安全 → 屏幕录制，确保终端已授权\n2. 确保屏幕未被锁定\n3. 检查显示器是否正常连接\n4. 尝试 pip install --upgrade pillow pyautogui\n5. 查看上面的完整错误堆栈"

def click_screen(x: int, y: int) -> str:
    """
    在屏幕指定的像素坐标 (x, y) 位置进行鼠标左键单击。
    一般用于配合截屏技能一起使用，先截屏看清屏幕上各个元素的位置，然后点击对应坐标。
    :param x: 点击目标在屏幕上的横向像素坐标
    :param y: 点击目标在屏幕上的纵向像素坐标
    :return: 操作结果
    """
    try:
        import pyautogui
    except ImportError:
        return "点击失败：请先 pip install pyautogui"
    
    print(f"\n[🔧 RPA执行] 正在点击屏幕坐标 ({x}, {y}) ...")
    try:
        pyautogui.click(x, y)
        time.sleep(0.3) # 等待界面反应
        return f"已成功在屏幕坐标 ({x}, {y}) 处执行了鼠标左键单击。建议您立刻再次调用 take_screenshot 截屏工具来确认点击后界面发生了什么变化。"
    except Exception as e:
        return f"点击失败: {str(e)}"

def read_webpage(url: str) -> str:
    """
    访问指定的网页 URL，读取并提取其中的纯文本内容。
    当需要获取具体网页的内容、阅读新闻文章、查看特定链接时调用。
    """

    print(f"\n[🔧 工具执行] 正在抓取并阅读网页: {url} ...")
    try:
        # 伪装成浏览器的主流 User-Agent 避免被反爬虫轻易拦截
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        # 解决乱码问题，自动推断网页编码
        response.encoding = response.apparent_encoding 
        response.raise_for_status()
        
        # 使用 BeautifulSoup 提取纯文本，筛掉杂乱的标签
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 移除掉无用的不可见元素和导航栏等噪音
        for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
            script_or_style.extract()
            
        text = soup.get_text(separator='\n', strip=True)
        
        # 截断过长的文本，防止网页文字太多撑爆大模型长文本上下文
        if len(text) > 8000:
            text = text[:8000] + "\n\n...[网页内容过长，后缀已截断]..."
            
        return f"网页 {url} 的内容提取成功：\n{text}"
    except Exception as e:
        return f"读取网页失败: {str(e)}"

def read_wechat_messages(contact_name: str = "") -> str:
    """
    读取微信当前聊天窗口中的消息内容。如果指定了联系人名字，会先搜索并进入该联系人的聊天窗口。
    通过截屏 + 视觉大模型(VLM)来提取聊天记录。
    :param contact_name: 可选，要查看消息的联系人名字。留空则读取当前已打开的聊天窗口。
    :return: 提取到的消息内容摘要
    """
    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return "执行失败：请先 pip install pyautogui pyperclip"

    print(f"\n[🔧 RPA执行] 正在读取微信消息...")

    # 第一步：确保微信在前台
    focus_result = _ensure_wechat_focused()
    if not focus_result["success"]:
        return f"读取微信消息失败：{focus_result['message']}"

    try:
        # 如果指定了联系人，先导航到该聊天窗口
        if contact_name.strip():
            print(f"[🔧 RPA执行] 正在搜索联系人: {contact_name}")
            
            # 策略：如果当前已经在聊天框内，多按几次 esc 可能会导致整个微信窗口失去焦点。
            # 为了稳定，我们在 Mac 微信下统一策略：直接按下 Cmd+F 进行群局搜索
            time.sleep(0.3) # 等待微信激活
            
            # Cmd+F 打开搜索
            _run_applescript('tell application "System Events" to keystroke "f" using command down')
            time.sleep(0.3)

            # 粘贴联系人名字
            pyperclip.copy(contact_name)
            _run_applescript('tell application "System Events" to keystroke "v" using command down')
            time.sleep(0.3)

            # 回车进入聊天
            _run_applescript('tell application "System Events" to key code 36') # Enter
            time.sleep(0.3)

            # 搜索完回车之后，按一次下键，再按一次上键，真正激活并锁定聊天框
            _run_applescript('tell application "System Events" to key code 125') # Down
            time.sleep(0.3)
            _run_applescript('tell application "System Events" to key code 126') # Up
            time.sleep(0.3)

        # 第二步：截屏并用 VLM 分析聊天内容
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"/tmp/wechat_read_{timestamp}.png"

        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_path)

        vision_result = analyze_image(
            screenshot_path,
            "这是微信桌面版的屏幕截图。请你仔细阅读并提取聊天窗口中的所有消息内容。"
            "对于每条消息，请按以下格式列出：\n"
            "- 【发送者】消息内容 (时间，如果能看到的话)\n"
            "请特别注意区分哪些是我发的消息（通常在右侧/绿色气泡），哪些是对方发的（通常在左侧/白色气泡）。\n"
            "同时请描述左侧聊天列表中有哪些联系人显示了未读消息（红色数字角标）。"
        )

        return f"微信消息读取完毕（截屏保存于: {screenshot_path}）\n\n{vision_result}"

    except Exception as e:
        error_msg = str(e)
        print(f"[❌ 微信消息读取错误] {error_msg}")
        import traceback
        traceback.print_exc()
        return f"❌ 读取微信消息时出错:\n{error_msg}\n\n💡 排查步骤：\n1. 确保微信已打开并已登录\n2. 确保 pyautogui 和 pillow 已安装 （pip install pyautogui pillow）\n3. 检查 /tmp 目录是否可写\n4. 查看上面的完整错误堆栈\n5. 确认好友名称拼写正确：{contact_name if contact_name.strip() else '(当前窗口模式)'}"


def send_wechat_message(contact_name: str, message: str) -> str:
    """
    通过模拟键盘鼠标操作(RPA)，自动给微信好友发送消息。(仅限 Mac 系统)
    """
    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return "执行失败：请先在终端运行 ctrl+c 退出，并执行 `pip install pyautogui pyperclip`"
    
    print(f"\n[🔧 RPA执行] 正在准备向微信好友 '{contact_name}' 发送消息...")
    
    # 第一步：使用 AppleScript 可靠地激活微信窗口
    focus_result = _ensure_wechat_focused()
    if not focus_result["success"]:
        return f"微信消息发送失败：{focus_result['message']}"
    
    print(f"[✅ 窗口聚焦] {focus_result['message']}")
    
    try:
        # 【修改策略】：如果当前已经在和目标的聊天框内，狂点 ESC 反而可能导致焦点异常甚至退出应用前台。
        # 稳妥的方式：直接按下 Command + F 聚焦到全局搜索框
        time.sleep(0.3) # 给微信激活一点反应时间
        
        # Cmd+F 打开搜索
        _run_applescript('tell application "System Events" to keystroke "f" using command down')
        time.sleep(0.3) # 等待搜索框聚焦
        
        # 输入好友名字
        pyperclip.copy(contact_name)
        _run_applescript('tell application "System Events" to keystroke "v" using command down')
        time.sleep(0.3) # 给微信充足的时间从本地拉取搜索结果
        
        # 5. 按回车键选中第一个搜索结果，进入聊天窗口
        _run_applescript('tell application "System Events" to key code 36') # Enter
        time.sleep(0.3)
        
        # 5.5 【终极 RPA 技巧】搜索完回车之后，按一次下键，再按一次上键，真正激活并锁定聊天框
        _run_applescript('tell application "System Events" to key code 125') # Down
        time.sleep(0.3)
        _run_applescript('tell application "System Events" to key code 126') # Up
        time.sleep(0.3)
        
        # 6. 输入你要发送的消息内容
        pyperclip.copy(message)
        _run_applescript('tell application "System Events" to keystroke "v" using command down')
        time.sleep(0.3)
        
        # 7. 按回车键发送！
        _run_applescript('tell application "System Events" to key code 36') # Enter
        
        return f"已成功通过 RPA 将消息 '{message}' 给微信好友 {contact_name} 发送出去了！"
    except Exception as e:
        return f"微信消息发送失败：{str(e)}\n请检查：1) 系统偏好设置 → 隐私与安全 → 辅助功能 中是否已授权终端 2) 微信是否已登录"

def read_qq_messages(contact_name: str = "") -> str:
    """
    读取QQ当前聊天窗口中的消息内容。如果指定了联系人名字，会先搜索并进入该联系人的聊天窗口。
    通过截屏 + 视觉大模型(VLM)来提取聊天记录。
    :param contact_name: 可选，要查看消息的联系人名字。留空则读取当前已打开的聊天窗口。
    :return: 提取到的消息内容摘要
    """
    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return "执行失败：请先 pip install pyautogui pyperclip"

    print(f"\n[🔧 RPA执行] 正在读取QQ消息...")

    # 第一步：确保QQ在前台
    focus_result = _ensure_qq_focused()
    if not focus_result["success"]:
        return f"读取QQ消息失败：{focus_result['message']}"

    try:
        # 如果指定了联系人，先导航到该聊天窗口
        if contact_name.strip():
            print(f"[🔧 RPA执行] 正在搜索联系人: {contact_name}")
            
            # 策略：如果当前已经在聊天框内，多按几次 esc 可能会导致整个QQ窗口失去焦点。
            # 为了稳定，直接按下 Cmd+F 进行群局搜索
            time.sleep(0.3) # 等待QQ激活
            
            # Cmd+F 打开搜索
            _run_applescript('tell application "System Events" to keystroke "f" using command down')
            time.sleep(0.3)

            # 粘贴联系人名字
            pyperclip.copy(contact_name)
            _run_applescript('tell application "System Events" to keystroke "v" using command down')
            time.sleep(0.3)

            # 回车进入聊天
            _run_applescript('tell application "System Events" to key code 36') # Enter
            time.sleep(0.3)

            # 搜索完回车之后，按一次下键，再按一次上键，真正激活并锁定聊天框
            _run_applescript('tell application "System Events" to key code 125') # Down
            time.sleep(0.3)
            _run_applescript('tell application "System Events" to key code 126') # Up
            time.sleep(0.3)

        # 第二步：截屏并用 VLM 分析聊天内容
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"/tmp/qq_read_{timestamp}.png"

        try:
            print(f"[📸 截屏] 正在截屏...")
            screenshot = pyautogui.screenshot()
            if screenshot is None:
                return f"❌ QQ消息读取失败：截屏返回 None\n\n💡 可能原因：\n1. 屏幕被锁定\n2. macOS 屏幕录制权限不足\n3. 显示器断开连接\n\n解决方案：检查系统偏好设置 → 隐私与安全 → 屏幕录制"
            print(f"[📸 保存] 图片尺寸: {screenshot.size}，正在保存...")
            screenshot.save(screenshot_path)
            if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) == 0:
                return f"❌ QQ消息读取失败：截屏文件无效"
        except Exception as screenshot_error:
            error_msg = str(screenshot_error)
            print(f"[❌ 截屏错误] {error_msg}")
            import traceback
            traceback.print_exc()
            return f"❌ QQ消息读取失败（截屏阶段）:\n{error_msg}\n\n💡 解决方案：\n1. 检查系统偏好设置 → 隐私与安全 → 屏幕录制，给终端授权\n2. 确保屏幕未被锁定\n3. 运行：pip install --upgrade pillow pyautogui"

        vision_result = analyze_image(
            screenshot_path,
            "这是QQ桌面版的屏幕截图。请你仔细阅读并提取聊天窗口中的所有消息内容。"
            "对于每条消息，请按以下格式列出：\n"
            "- 【发送者】消息内容 (时间，如果能看到的话)\n"
            "请特别注意区分哪些是我发的消息（通常在右侧/不同颜色），哪些是对方发的（通常在左侧）。\n"
            "同时请描述左侧聊天列表中有哪些联系人显示了未读消息（红色数字角标）。"
        )

        return f"QQ消息读取完毕（截屏保存于: {screenshot_path}）\n\n{vision_result}"

    except Exception as e:
        error_msg = str(e)
        print(f"[❌ QQ消息读取错误] {error_msg}")
        import traceback
        traceback.print_exc()
        return f"❌ 读取QQ消息时出错:\n{error_msg}\n\n💡 排查步骤：\n1. 确保 QQ 已打开并已登录\n2. 确保 pyautogui 和 pillow 已安装 （pip install pyautogui pillow）\n3. 检查 /tmp 目录是否可写\n4. 查看上面的完整错误堆栈\n5. 确认好友名称拼写正确：{contact_name if contact_name.strip() else '(当前窗口模式)'}"

def send_qq_message(contact_name: str, message: str) -> str:
    """
    通过模拟键盘鼠标操作(RPA)，自动给QQ好友发送消息。(仅限 Mac 系统)
    """
    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return "执行失败：请先在终端运行 ctrl+c 退出，并执行 `pip install pyautogui pyperclip`"
    
    print(f"\n[🔧 RPA执行] 正在准备向QQ好友 '{contact_name}' 发送消息...")
    
    # 第一步：可靠地激活QQ窗口
    focus_result = _ensure_qq_focused()
    if not focus_result["success"]:
        return f"QQ消息发送失败：{focus_result['message']}"
    
    print(f"[✅ 窗口聚焦] {focus_result['message']}")
    
    try:
        # 直接按下 Command + F 聚焦到全局搜索框
        time.sleep(0.3) # 给QQ激活一点反应时间
        
        _run_applescript('tell application "System Events" to keystroke "f" using command down')
        time.sleep(0.3) # 等待搜索框聚焦
        
        # 输入好友名字
        pyperclip.copy(contact_name)
        _run_applescript('tell application "System Events" to keystroke "v" using command down')
        time.sleep(0.3) # 给QQ充足的时间从本地拉取搜索结果
        
        # 按回车键选中第一个搜索结果，进入聊天窗口
        _run_applescript('tell application "System Events" to key code 36') # Enter
        time.sleep(0.3)
        
        # 搜索完回车之后，按一次下键，再按一次上键，真正激活并锁定聊天框
        _run_applescript('tell application "System Events" to key code 125') # Down
        time.sleep(0.3)
        _run_applescript('tell application "System Events" to key code 126') # Up
        time.sleep(0.3)
        
        # 输入你要发送的消息内容
        pyperclip.copy(message)
        _run_applescript('tell application "System Events" to keystroke "v" using command down')
        time.sleep(0.3)
        
        # 按回车键发送！
        _run_applescript('tell application "System Events" to key code 36') # Enter
        
        return f"已成功通过 RPA 将消息 '{message}' 给QQ好友 {contact_name} 发送出去了！"
    except Exception as e:
        return f"QQ消息发送失败：{str(e)}\n请检查：1) 系统偏好设置 → 隐私与安全 → 辅助功能 中是否已授权终端 2) QQ是否已登录"


def auto_fill_web_form(
    url: str,
    form_data: dict,
    submit_button_selector: str = "",
    headless: bool = True,
    timeout: int = 30,
    chrome_user_data_dir: str = "",
    chrome_profile: str = "Default",
) -> str:
    """
    自动化打开网页并填充表单字段。建议用于支持标准 HTML 表单的页面。

    :param url: 目标网页地址
    :param form_data: 字段和值的映射, 例如 {"username": "张三", "email": "a@b.com"}
                      也支持更细粒度对象：{"selector": "#id", "value": "xxx"}
    :param submit_button_selector: 可选的提交按钮CSS/XPath选择器，若为空则尝试找到第一个type=submit按钮。
    :param headless: 是否以无头模式启动浏览器
    :param timeout: 等待页面或元素加载的超时时间（秒）
    :param chrome_user_data_dir: Chrome/Edge 用户数据目录路径，用于复用已登录 Cookie（如 /Users/xxx/Library/Application Support/Google/Chrome）
    :param chrome_profile: 要复用的 Chrome 个人资料目录名（例如 Default、Profile 1）
    :return: 执行结果描述
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
    except ImportError:
        return (
            "自动填写表单失败：未安装 selenium。\n"
            "请执行 `pip install selenium`。\n"
            "如果你使用 Chrome，可能还需要安装 chromedriver 或使用 webdriver-manager。"
        )

    if not isinstance(form_data, dict):
        return "自动填写表单失败：form_data 必须是一个字典。"

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1600,1200')

    # 允许复用手动登录的浏览器会话（用户已提前登录）
    if chrome_user_data_dir:
        options.add_argument(f"--user-data-dir={chrome_user_data_dir}")
        if chrome_profile:
            options.add_argument(f"--profile-directory={chrome_profile}")

    # 优先使用系统可用的Chrome/Chromium
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        return f"自动填写表单失败：启动 Chrome 驱动失败，可能缺少 chromedriver 或浏览器，错误：{e}"

    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)

        wait = WebDriverWait(driver, timeout)
        wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')

        fill_logs = []

        def _find_element_plain(key, value):
            # 先尝试 id/name，后尝试css和xpath
            for by, val in [(By.NAME, key), (By.ID, key)]:
                try:
                    return driver.find_element(by, val)
                except NoSuchElementException:
                    continue

            # 可能 key 本身是css或xpath
            try:
                if key.startswith('/') or key.startswith('('):
                    return driver.find_element(By.XPATH, key)
                return driver.find_element(By.CSS_SELECTOR, key)
            except Exception:
                return None

        for field_key, field_value in form_data.items():
            target_selector = None
            value = field_value
            if isinstance(field_value, dict):
                value = field_value.get('value')
                target_selector = field_value.get('selector', '')

            el = None
            if target_selector:
                try:
                    if target_selector.startswith('/') or target_selector.startswith('('):
                        el = driver.find_element(By.XPATH, target_selector)
                    else:
                        el = driver.find_element(By.CSS_SELECTOR, target_selector)
                except Exception:
                    el = None
            if not el:
                el = _find_element_plain(field_key, value)

            if not el:
                fill_logs.append(f"跳过字段 {field_key}：未找到对应元素")
                continue

            tag = el.tag_name.lower()

            try:
                if tag == 'select':
                    sel = Select(el)
                    try:
                        sel.select_by_value(str(value))
                    except Exception:
                        sel.select_by_visible_text(str(value))
                    fill_logs.append(f"已为下拉域 {field_key} 选中 {value}")
                    continue

                if tag == 'input' and el.get_attribute('type') in ['checkbox', 'radio']:
                    should_check = bool(value)
                    if el.is_selected() != should_check:
                        el.click()
                    fill_logs.append(f"已为复选/单选域 {field_key} 设为 {should_check}")
                    continue

                el.clear()
                el.send_keys(str(value))
                fill_logs.append(f"已为字段 {field_key} 填入: {value}")
            except Exception as e:
                fill_logs.append(f"字段 {field_key} 填写失败: {e}")

        if submit_button_selector:
            submit_el = None
            try:
                if submit_button_selector.startswith('/') or submit_button_selector.startswith('('):
                    submit_el = driver.find_element(By.XPATH, submit_button_selector)
                else:
                    submit_el = driver.find_element(By.CSS_SELECTOR, submit_button_selector)
                submit_el.click()
                fill_logs.append(f"已点击提交按钮: {submit_button_selector}")
            except Exception as e:
                fill_logs.append(f"指定提交按钮点击失败: {e}")
        else:
            # 找到默认提交按钮
            try:
                submit_el = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
                submit_el.click()
                fill_logs.append("已点击默认提交按钮")
            except Exception:
                fill_logs.append("未找到可点击的提交按钮，未执行提交操作")

        # 等待短时间，让提交或页面变化完成
        time.sleep(0.3)

        return "\n".join(["自动填写表单已执行，详情："] + fill_logs)

    except TimeoutException:
        return "自动填写表单失败：页面加载超时。"
    except Exception as e:
        return f"自动填写表单失败：{e}"
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def find_local_file(filename: str, search_dir: str = "~") -> str:
    """
    在指定目录及其子文件夹中搜索指定名字的文件
    :param filename: 文件名（精确匹配）
    :param search_dir: 搜索范围，默认为 ~ (用户主目录)
    :return: 找到的绝度路径列表
    """
    search_dir = os.path.expanduser(search_dir)
    print(f"\n[🔧 工具执行] 正在你的电脑中搜索文件: {filename} (范围: {search_dir}) ...")
    
    found_paths = []
    try:
        # os.walk 能深入遍历所有子文件夹
        for root, dirs, files in os.walk(search_dir):
            # 过滤掉一些庞大的无关文件夹，加快搜索速度
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('Library', 'node_modules', 'venv')]
            
            if filename in files:
                found_paths.append(os.path.join(root, filename))
                # 找到前 5 个满意的就行了，防止文件太多或者卡死
                if len(found_paths) >= 5:
                    break
                    
        if not found_paths:
            return f"未能找到文件名为 {filename} 的文件。"
            
        return "找到以下可能的文件:\n" + "\n".join(found_paths)
    except Exception as e:
        return f"自动搜寻文件时出错: {str(e)}"

def read_file(file_path: str) -> str:
    """
    读取本地文件内容
    :param file_path: 文件路径
    :return: 文件内容或错误信息
    """
    file_path = os.path.expanduser(file_path)
    print(f"\n[🔧 工具执行] 正在读取文件: {file_path} ...")
    try:
        if not os.path.exists(file_path):
            return f"错误：文件 {file_path} 不存在。"
            
        # 如果是 Word 文档，使用 docx 包读取
        if file_path.lower().endswith('.docx'):
            doc = docx.Document(file_path)
            # 将所有段落提取合并
            content = "\n".join([para.text for para in doc.paragraphs])
            return f"Word 文档 {file_path} 内容如下:\n{content}"
        
        # 否则默认使用纯文本读取方式
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"文件 {file_path} 内容如下:\n{content}"
    except Exception as e:
        return f"读取文件失败: {str(e)}"

def write_file(file_path: str, content: str) -> str:
    """
    向本地文件写入内容 (会覆盖原内容)
    :param file_path: 文件路径
    :param content: 要写入的内容
    :return: 执行结果信息
    """
    file_path = os.path.expanduser(file_path)
    print(f"\n[🔧 工具执行] 正在写入文件: {file_path} ...")
    try:
        # 确保文件的父目录存在
        dir_name = os.path.dirname(os.path.abspath(file_path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功将文本内容写入到文件 {file_path}。"
    except Exception as e:
        return f"写入文件失败: {str(e)}"

# ====== 工具的描述信息 ======
# 大模型并不能直接看到上面写的 Python 代码。
# 我们必须告诉模型：“这是你拥有的技能列表，每个技能(function)叫什么名字，需要传什么参数”。
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "当且仅当需要知道最新信息、客观事实或回答不知道的问题时，使用此工具搜索互联网。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的准确关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "访问指定的网页 URL，读取并提取其中的纯文本内容。当用户提供具体的网址，或者搜索完想让你深入查看某一个具体的网页详情时调用。只能读取静态网页，无法突破需要登录或高强度人机验证的网站。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "需要访问的完整网页 URL，必须以 http:// 或 https:// 开头"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "auto_fill_web_form",
            "description": "自动打开网页并填写表单字段，可以指定字段名或 CSS/XPath 选择器，支持可选提交按钮。适用于标准 HTML 表单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "表单页面地址，必须以 http:// 或 https:// 开头"
                    },
                    "form_data": {
                        "type": "object",
                        "description": "字段值映射，例如 {\"username\": \"张三\", \"email\": \"a@b.com\"}。也支持复杂格式：{\"fieldName\": {\"selector\": \"#id\", \"value\": \"xxx\"}}。"
                    },
                    "submit_button_selector": {
                        "type": "string",
                        "description": "可选的提交按钮 CSS 或 XPath 定位表达式，缺省时会尝试寻找默认提交按钮。"
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "是否无头模式运行 Selenium 浏览器。"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "页面加载超时时间（秒）。"
                    }
                },
                "required": ["url", "form_data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "这是你的【眼睛】。当用户让你看一张电脑里的图片、帮你分辨图片内容、提取图片里的文字，或者询问任意关于某张本地图片的问题时，必须调用这个专门的视觉子模型来帮你代看。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "图片文件的本地绝对路径或相对路径，比如 /Users/xxx/Desktop/img.png"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "你希望负责看图的视觉模型去帮你提取什么重点？例如：'帮我把这张发票图片里的金额提取出来' 或 '非常仔细地向我描述画面中这只鸟的颜色和形态'"
                    }
                },
                "required": ["image_path", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "对当前屏幕进行截屏并自动调用视觉大模型分析截图内容。这是你的【实时眼睛】，用于当你需要“看一眼”当前未知的屏幕内容。\n⚠️ 注意：如果要查看微信聊天消息，【绝对禁止调用此工具】，必须直接调用专用的 `read_wechat_messages` 工具！",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_screen",
            "description": "在屏幕指定的像素坐标(x, y)上执行鼠标左键单击。\n⚠️ 注意：如果要发送微信消息，【绝对禁止调用此工具进行瞎点】，必须直接调用专用的 `send_wechat_message` 工具！",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "点击目标在屏幕上的横向像素 X 坐标"
                    },
                    "y": {
                        "type": "integer",
                        "description": "点击目标在屏幕上的纵向像素 Y 坐标"
                    }
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_local_file",
            "description": "当用户只记得文件名，但不记得文件的绝对路径具体在哪时，可以用此工具在本地电脑里寻找该文件的确切路径。找到路径后可以再用读取文件的工具去读取它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "要寻找的具体文件名，需要带后缀名，例如 config.json"
                    },
                    "search_dir": {
                        "type": "string",
                        "description": "你想搜索的起始目录。如果不确定，请默认填写 '~' 代表从用户的整个根目录开始搜索。"
                    }
                },
                "required": ["filename", "search_dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_wechat_message",
            "description": "当且仅当用户明确要求【给某人发微信】、【回复微信】时调用。通过物理模拟键盘(RPA)自动向指定的微信收件人发送消息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "要发送的微信好友、同事或群的确切备注名，例如 '阿甘'、'文件传输助手'"
                    },
                    "message": {
                        "type": "string",
                        "description": "大模型起草好的想要发送的微信详细文本内容"
                    }
                },
                "required": ["contact_name", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_wechat_messages",
            "description": "当且仅当用户要求【读微信】、【查看微信聊天记录】、【看看刚才谁发了微信】时调用。自动读取并提取前台微信聊天窗口内容。如果给定了联系人名字，会先跳转到该好友的聊天框再读取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "（可选）想要查看聊天记录的具体微信好友备注名或群名。如果留空，则读取当前正处于打开状态的聊天窗口。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_qq_messages",
            "description": "当且仅当用户要求【读QQ】、【查看QQ聊天记录】、【查看指定QQ好友消息】时调用。自动读取并提取前台QQ聊天窗口内容。如果给定了联系人名字，会先跳转到该好友的聊天框再读取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "（可选）想要查看QQ聊天记录的具体QQ好友备注名、昵称或群名。如果留空，则读取当前正处于打开状态的聊天窗口。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_qq_message",
            "description": "当且仅当用户明确要求【给某人发QQ】、【回复QQ】时调用。通过物理模拟键盘(RPA)自动向指定的QQ收件人发送消息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "要发送的QQ好友或群的确切名称，例如 '张三'"
                    },
                    "message": {
                        "type": "string",
                        "description": "大模型起草好的想要发送的QQ详细文本内容"
                    }
                },
                "required": ["contact_name", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本地相对应路径的文件内容。用以获知文件中的文字信息。不仅支持常见的纯文本(.txt, .md, .py, .json等代码)，也完美支持读取复杂的 Office Word 文档 (.docx)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "本地文件的绝对或相对路径"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将被要求的信息保存或写入到本地指定文件中，支持创建新文件。该操作会覆盖同名文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "想要保存的本地文件的绝对或相对路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "想要写入的具体文本内容"
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    }
]

# 用于在代码层面映射大模型返回的"函数名字字符串"到实际的"Python函数本身"
TOOLS_MAP = {
    "search_web": search_web,
    "read_webpage": read_webpage,
    "auto_fill_web_form": auto_fill_web_form,
    "analyze_image": analyze_image,
    "take_screenshot": take_screenshot,
    "click_screen": click_screen,
    "find_local_file": find_local_file,
    "read_wechat_messages": read_wechat_messages,
    "send_wechat_message": send_wechat_message,
    "read_qq_messages": read_qq_messages,
    "send_qq_message": send_qq_message,
    "read_file": read_file,
    "write_file": write_file
}
