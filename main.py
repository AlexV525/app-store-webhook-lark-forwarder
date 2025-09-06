import base64
import hashlib
import hmac
import json
import os
import requests
import time

# 建议通过环境变量来设置这些敏感信息，而不是硬编码在代码里
LARK_WEBHOOK_URL = os.environ.get('LARK_WEBHOOK_URL')
LARK_SIGNING_SECRET = os.environ.get('LARK_SIGNING_SECRET') # Lark机器人的签名密钥
APP_STORE_CONNECT_SECRET = os.environ.get('APP_STORE_CONNECT_SECRET')

def verify_apple_signature(request):
    """
    验证来自 App Store Connect 的请求签名。
    增加了详细的日志输出，方便调试。
    """
    signature_header = request.headers.get('X-Apple-Signature')
    if not signature_header:
        print("【错误】请求头中缺少 'X-Apple-Signature'，验证失败。")
        return False

    if not APP_STORE_CONNECT_SECRET:
        print("【严重错误】环境变量 'APP_STORE_CONNECT_SECRET' 未设置，无法验证签名。请检查您的云函数配置。")
        return False

    # 苹果发送的签名格式为 "hmacsha256=..."，我们需要先分离出真正的签名部分
    try:
        signature_algorithm, received_signature = signature_header.split('=', 1)
        if signature_algorithm != 'hmacsha256':
            print(f"【错误】不支持的签名算法: {signature_algorithm}")
            return False
    except ValueError:
        print(f"【错误】签名头格式不正确: {signature_header}")
        return False


    # 获取原始的请求体（raw body）
    request_body = request.get_data()

    # 使用 HMAC-SHA256 算法计算签名
    hashed = hmac.new(
        APP_STORE_CONNECT_SECRET.encode('utf-8'),
        msg=request_body,
        digestmod=hashlib.sha256
    )

    # 【修复】将计算出的签名转换为十六进制字符串，而不是 Base64
    expected_signature = hashed.hexdigest()

    # 【调试日志】打印收到的和计算出的签名
    print("--- 签名验证调试信息 ---")
    print(f"收到的签名 (来自 Apple): {received_signature}")
    print(f"计算的签名 (来自函数): {expected_signature}")
    print("--------------------------")

    # 使用 hmac.compare_digest 来安全地比较两个签名，可防止时序攻击
    if not hmac.compare_digest(expected_signature, received_signature):
        print("【验证失败】签名不匹配。请再次确认您的密钥是正确的。如果问题仍然存在，请检查代码。")
        return False

    print("【成功】签名验证通过。")
    return True

def format_lark_card(data):
    """
    将 App Store Connect 的 Webhook 数据格式化为 Lark 卡片消息。
    """
    try:
        # 提取核心信息
        webhook_data = data.get('data', {})
        attributes = webhook_data.get('attributes', {})
        relationships = webhook_data.get('relationships', {})

        event_type = webhook_data.get('type')
        app_name = relationships.get('app', {}).get('data', {}).get('attributes', {}).get('name', '未知应用')

        title = f"📱 App Store Connect 通知"
        content_lines = [f"**应用**: {app_name}"]

        # 根据不同的事件类型，生成不同的消息内容
        if event_type == 'appStoreVersionStateUpdated':
            title = f"📱 版本状态更新 - {app_name}"
            version_string = attributes.get('versionString', 'N/A')
            old_state = attributes.get('oldState', 'N/A').replace('_', ' ').title()
            new_state = attributes.get('newState', 'N/A').replace('_', ' ').title()
            content_lines = [
                f"**版本**: {version_string}",
                f"**状态变更**: `{old_state}` → `{new_state}`"
            ]
        elif event_type == 'buildStateUpdated':
            title = f"🛠️ 构建版本状态更新 - {app_name}"
            version = attributes.get('version', 'N/A')
            old_state = attributes.get('oldState', 'N/A').replace('_', ' ').title()
            new_state = attributes.get('newState', 'N/A').replace('_', ' ').title()
            content_lines = [
                f"**版本 (构建号)**: {version}",
                f"**状态变更**: `{old_state}` → `{new_state}`"
            ]
        elif event_type and 'FEEDBACK' in event_type.upper():
            title = f"💬 新的 TestFlight 反馈 - {app_name}"
            content_lines.append("**您收到了新的 TestFlight 用户反馈，请及时登录后台查看。**")
        else:
            # 对于其他未知类型的通知，显示原始类型
            content_lines.append(f"**事件类型**: `{event_type}`")
            content_lines.append("这是一个未特别处理的通知类型，请登录后台查看详情。")

        # 构建 Lark 卡片消息的 JSON 结构
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue" # 你可以根据喜好更改颜色: blue, wathet, turquoise, green, yellow, orange, red, carmine, violet, purple, indigo
                },
                "elements": [{
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n".join(content_lines)
                    }
                }]
            }
        }
    except Exception as e:
        print(f"格式化 Lark 消息时出错: {e}")
        # 返回一个简单的文本消息作为降级方案
        return {
            "msg_type": "text",
            "content": {"text": f"处理 App Store 通知时出错。\n原始数据:\n{json.dumps(data, indent=2)}"}
        }

def webhook_handler(request):
    """
    云函数的入口点，处理所有传入的 HTTP 请求。
    """
    # 仅接受 POST 请求
    if request.method != 'POST':
        return '仅支持 POST 方法', 405

    # 验证请求签名
    if not verify_apple_signature(request):
        return '签名验证失败，请求被拒绝。', 403

    # 解析 JSON 数据
    try:
        data = request.get_json(silent=True)
        if data is None:
            return '请求体不是有效的 JSON 格式。', 400
        print(f"收到并解析了 JSON 数据: {json.dumps(data)}")
    except Exception as e:
        print(f"解析 JSON 时出错: {e}")
        return '无效的 JSON 数据。', 400

    # 检查环境变量是否配置
    if not LARK_WEBHOOK_URL:
        error_msg = "服务器配置错误: LARK_WEBHOOK_URL 环境变量未设置。"
        print(error_msg)
        return error_msg, 500

    # 格式化消息并发送到 Lark
    lark_message = format_lark_card(data)

    # 如果配置了 Lark 签名密钥，则为消息添加签名
    if LARK_SIGNING_SECRET:
        timestamp = str(int(time.time()))

        # 根据 Lark 的文档，拼接 timestamp 和密钥，然后进行 HmacSHA256 计算
        string_to_sign = f"{timestamp}\n{LARK_SIGNING_SECRET}"

        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            msg=None, # Lark 的签名方法比较特殊，消息体为空
            digestmod=hashlib.sha256
        ).digest()

        sign = base64.b64encode(hmac_code).decode('utf-8')

        # 将 timestamp 和 sign 添加到 payload 的顶层
        lark_message['timestamp'] = timestamp
        lark_message['sign'] = sign
        print("已为 Lark 消息生成签名。")

    try:
        response = requests.post(LARK_WEBHOOK_URL, json=lark_message, timeout=10)
        response.raise_for_status()  # 如果 HTTP 状态码是 4xx 或 5xx，则抛出异常
        print(f"成功发送消息到 Lark, 响应: {response.text}")
        return '通知已成功转发到 Lark', 200
    except requests.exceptions.RequestException as e:
        print(f"发送消息到 Lark 时出错: {e}")
        return '转发到 Lark 时出错', 502


