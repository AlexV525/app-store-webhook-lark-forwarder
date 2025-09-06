import base64
import hashlib
import hmac
import json
import os
import requests
import time
import argparse

# --- 环境变量读取 ---
# 用于接收 App Store 通知的 Webhook
LARK_WEBHOOK_URL = os.environ.get('LARK_WEBHOOK_URL')
LARK_SIGNING_SECRET = os.environ.get('LARK_SIGNING_SECRET')
# 用于接收 Apple Webhook 的密钥
APP_STORE_CONNECT_SECRET = os.environ.get('APP_STORE_CONNECT_SECRET')

# --- 核心辅助函数 ---

def generate_lark_signature(secret: str, timestamp: int) -> str:
    """根据时间戳和密钥生成飞书/Lark的签名"""
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode('utf-8')
    return sign

def send_lark_notification(webhook_url: str, secret: str, card_payload: dict):
    """
    发送卡片消息到指定的飞书/Lark Webhook。
    如果提供了 secret，会自动处理签名。
    """
    if not webhook_url:
        print("错误：Webhook URL 未提供。")
        return

    headers = {'Content-Type': 'application/json'}

    if secret:
        timestamp = int(time.time())
        signature = generate_lark_signature(secret, timestamp)
        card_payload['timestamp'] = timestamp
        card_payload['sign'] = signature

    try:
        response = requests.post(webhook_url, headers=headers, json=card_payload)
        response.raise_for_status()
        response_data = response.json()
        if response_data.get("StatusCode") == 0 or response_data.get("code") == 0:
            print("消息成功发送到飞书/Lark。")
        else:
            print(f"发送到飞书/Lark时返回错误: {response_data}")
    except requests.exceptions.RequestException as e:
        print(f"发送到飞书/Lark时发生网络错误: {e}")

def format_lark_card(title: str, content: str) -> dict:
    """构造一个标准的飞书/Lark卡片消息结构"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                }
            ]
        }
    }


def verify_apple_signature(request):
    """验证来自 App Store Connect 的请求签名"""
    signature_header = request.headers.get('X-Apple-Signature', '')

    # 移除 'hmacsha256=' 前缀 (如果有)
    if '=' in signature_header:
        algo, received_signature = signature_header.split('=', 1)
    else:
        received_signature = signature_header

    if not received_signature:
        print("签名头缺失。")
        return False

    if not APP_STORE_CONNECT_SECRET:
        print("APP_STORE_CONNECT_SECRET 未设置。")
        return False

    request_body = request.get_data()
    hashed = hmac.new(
        APP_STORE_CONNECT_SECRET.encode('utf-8'),
        msg=request_body,
        digestmod=hashlib.sha256
    )
    calculated_signature = hashed.hexdigest()

    return hmac.compare_digest(received_signature, calculated_signature)

def parse_apple_notification(data: dict) -> (str, str):
    """解析 Apple 的通知数据，返回标题和内容"""
    try:
        event_data = data.get('data', {})
        attributes = event_data.get('attributes', {})
        relationships = event_data.get('relationships', {})

        notification_type = event_data.get('type', '未知类型')
        app_name = relationships.get('app', {}).get('data', {}).get('attributes', {}).get('name', '未知应用')
        version = attributes.get('versionString', '')

        title = f"📱 {app_name} ({version})" if version else f"📱 {app_name}"
        lines = []

        if notification_type == 'APP_STORE_VERSION_STATE_UPDATED':
            old_state = attributes.get('oldState', 'N/A')
            new_state = attributes.get('newState', 'N/A')
            lines.append(f"**应用版本状态更新**")
            lines.append(f"旧状态: `{old_state}`")
            lines.append(f"新状态: `{new_state}`")
        elif notification_type == 'BUILD_STATE_UPDATED':
            old_state = attributes.get('oldState', 'N/A')
            new_state = attributes.get('newState', 'N/A')
            lines.append(f"**构建版本状态更新**")
            lines.append(f"构建版本: `{version}`")
            lines.append(f"旧状态: `{old_state}`")
            lines.append(f"新状态: `{new_state}`")
        elif 'FEEDBACK' in notification_type.upper():
            lines.append(f"**收到新的 TestFlight 反馈**")
            lines.append("请登录 App Store Connect 查看详情。")
        else:
            lines.append(f"**收到新通知**")
            lines.append(f"类型: `{notification_type}`")
            lines.append("请登录 App Store Connect 查看详情。")

        return title, "\n".join(lines)

    except Exception as e:
        print(f"解析通知时出错: {e}")
        return "⚠️ 通知解析错误", f"```json\n{json.dumps(data, indent=2)}\n```"

# --- Cloud Function 主入口 ---

def webhook_handler(request):
    """
    Google Cloud Function 的主入口函数。
    接收并处理来自 App Store Connect 的 POST 请求。
    """
    if request.method != 'POST':
        return '仅接受 POST 请求', 405

    if not verify_apple_signature(request):
        return '签名验证失败，请求被拒绝', 403

    try:
        data = request.get_json()
    except Exception as e:
        return f'无效的 JSON: {e}', 400

    title, content = parse_apple_notification(data)
    card_payload = format_lark_card(title, content)

    send_lark_notification(LARK_WEBHOOK_URL, LARK_SIGNING_SECRET, card_payload)

    return '通知已转发', 200

# --- 命令行调用入口 ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="发送一个卡片消息到飞书/Lark。")
    parser.add_argument('--title', required=True, help="卡片消息的标题")
    parser.add_argument('--content', required=True, help="卡片消息的内容 (Markdown 格式)")

    args = parser.parse_args()

    # 从环境变量读取 Webhook URL 和密钥
    cli_webhook_url = os.environ.get('LARK_WEBHOOK_URL')
    cli_signing_secret = os.environ.get('LARK_SIGNING_SECRET')

    if not cli_webhook_url:
        raise ValueError("错误: 必须在环境变量中设置 LARK_WEBHOOK_URL。")

    message_payload = format_lark_card(args.title, args.content)
    send_lark_notification(cli_webhook_url, cli_signing_secret, message_payload)

