from typing import Optional

import base64
import hashlib
import hmac
import json
import os
import requests
import time
import argparse
import jwt

# --- 环境变量读取 ---
# 用于接收 App Store 通知的 Webhook
LARK_WEBHOOK_URL = os.environ.get('LARK_WEBHOOK_URL')
LARK_SIGNING_SECRET = os.environ.get('LARK_SIGNING_SECRET')
# 用于接收 Apple Webhook 的密钥
APP_STORE_CONNECT_SECRET = os.environ.get('APP_STORE_CONNECT_SECRET')
# App Store Connect API 认证信息
KEY_ID = os.environ.get('KEY_ID')
ISSUER_ID = os.environ.get('ISSUER_ID')
APPSTORE_PRIVATE_KEY = os.environ.get('APPSTORE_PRIVATE_KEY')

# --- App Store Connect API ---

def generate_asc_token(scope: list[str]) -> str:
    """Generate the JWT for App Store Connect API authentication."""
    # Ensure the private key is formatted correctly with actual newlines
    private_key = APPSTORE_PRIVATE_KEY.replace('\n', '\n')
    
    payload = {
        "iss": ISSUER_ID,
        "iat": int(time.time()),
        "exp": int(time.time()) + 10 * 60, # Token valid for 10 minutes
        "aud": "appstoreconnect-v1",
        "scope": scope
    }
    encoded_token = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": KEY_ID}
    )
    return encoded_token.decode('utf-8')

def get_app_details_from_app_id(app_id: str) -> (Optional[str], Optional[str]):
    """Get app details by making a manual API call from an app ID."""
    scope = [f"GET /v1/apps/{app_id}"]
    token = generate_asc_token(scope=scope)
    headers = {'Authorization': f'Bearer {token}'}
    url = f"https://api.appstoreconnect.apple.com/v1/apps/{app_id}"

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()['data']

    app_name = data['attributes']['name']
    icon_url = None
    icon_token_data = data['attributes'].get('iconAssetToken')
    if icon_token_data:
        template_url = icon_token_data.get('templateUrl')
        if template_url:
            icon_url = template_url.format(w=100, h=100, f='png')
    return app_name, icon_url

def get_app_details_from_version_id(version_id: str) -> (Optional[str], Optional[str]):
    """Get app details by making a manual API call from a version ID."""
    scope = [f"GET /v1/appStoreVersions/{version_id}?include=app"]
    token = generate_asc_token(scope=scope)
    headers = {'Authorization': f'Bearer {token}'}
    url = f"https://api.appstoreconnect.apple.com/v1/appStoreVersions/{version_id}?include=app"

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    app_data = next((item for item in data.get('included', []) if item.get('type') == 'apps'), None)
    if not app_data:
        return None, None

    app_name = app_data['attributes'].get("name")
    icon_url = None
    icon_token_data = app_data['attributes'].get('iconAssetToken')
    if icon_token_data:
        template_url = icon_token_data.get('templateUrl')
        if template_url:
            icon_url = template_url.format(w=100, h=100, f='png')
    return app_name, icon_url

def get_app_details(app_id: Optional[str] = None, version_id: Optional[str] = None) -> (Optional[str], Optional[str]):
    """使用 App Store Connect API 获取应用名称和图标 URL"""
    if not all([KEY_ID, ISSUER_ID, APPSTORE_PRIVATE_KEY]) or not (app_id or version_id):
        print("缺少 App Store Connect API 凭证或 app_id/version_id。")
        return None, None

    try:
        if version_id:
            return get_app_details_from_version_id(version_id)
        if app_id:
            return get_app_details_from_app_id(app_id)

    except Exception as e:
        print(f"获取 App Store Connect API 数据时出错: {e}")
        return None, None

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

def format_lark_card(title: str, content: str, raw: Optional[str], icon_url: Optional[str]) -> dict:
    """构造一个标准的飞书/Lark卡片消息结构"""
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content
            }
        }
    ]
    if icon_url:
        elements[0]["extra"] = {
            "tag": "img",
            "img_key": icon_url,
            "alt": {
                "tag": "plain_text",
                "content": "应用图标"
            }
        }

    if raw:
        elements.append({
            "tag": "markdown",
            "content": f"```\n{raw}\n```"
        })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": elements
        }
    }


def verify_apple_signature(request):
    """验证来自 App Store Connect 的请求签名"""
    signature_header = request.headers.get('X-Apple-Signature', '')

    if '=' in signature_header:
        _, received_signature = signature_header.split('=', 1)
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
        digestmod= hashlib.sha256
    )
    calculated_signature = hashed.hexdigest()

    return hmac.compare_digest(received_signature, calculated_signature)

def parse_apple_notification(data: dict, app_name_override: Optional[str]) -> (str, str, str):
    """解析 Apple 的通知数据，返回标题和内容，并附带原始 JSON"""
    raw_json_block = json.dumps(data, indent=2, ensure_ascii=False)

    try:
        event_data = data.get('data', {})
        attributes = event_data.get('attributes', {})
        
        notification_type = event_data.get('type', '未知类型')
        version = attributes.get('versionString', '')

        app_name = app_name_override or '未知应用'
        title = f"📱 {app_name} ({version})" if version else f"📱 {app_name}"
        lines = []

        if notification_type == 'APP_STORE_VERSION_STATE_UPDATED':
            old_state = attributes.get('oldState', 'N/A')
            new_state = attributes.get('newState', 'N/A')
            lines.append(f"**应用版本状态更新**")
            lines.append(f"旧状态: `{old_state}`")
            lines.append(f"新状态: `{new_state}`")
        elif notification_type == 'appStoreVersionAppVersionStateUpdated':
            old_state = attributes.get('oldValue', 'N/A')
            new_state = attributes.get('newValue', 'N/A')
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

        content = "\n".join(lines)
        return title, content, raw_json_block

    except Exception as e:
        print(f"解析通知时出错: {e}")
        return "⚠️ 通知解析错误", f"{e}", raw_json_block

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

    app_name = None
    icon_url = None

    event_data = data.get('data', {})

    # Try to get app_id directly
    app_id = event_data.get('relationships', {}).get('app', {}).get('data', {}).get('id')
    version_id = None

    # If direct app_id is not found, try to get version_id from the instance relationship
    if not app_id:
        version_id = event_data.get('relationships', {}).get('instance', {}).get('data', {}).get('id')

    if app_id or version_id:
        app_name, icon_url = get_app_details(app_id=app_id, version_id=version_id)

    title, content, raw = parse_apple_notification(data, app_name)
    card_payload = format_lark_card(title, content, raw, icon_url)

    send_lark_notification(LARK_WEBHOOK_URL, LARK_SIGNING_SECRET, card_payload)

    return '通知已转发', 200

# --- 命令行调用入口 ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="发送一个卡片消息到飞书/Lark。")
    parser.add_argument('--title', required=True, help="卡片消息的标题")
    parser.add_argument('--content', required=True, help="卡片消息的内容 (Markdown 格式)")

    args = parser.parse_args()

    cli_webhook_url = os.environ.get('LARK_WEBHOOK_URL')
    cli_signing_secret = os.environ.get('LARK_SIGNING_SECRET')

    if not cli_webhook_url:
        raise ValueError("错误: 必须在环境变量中设置 LARK_WEBHOOK_URL。")

    message_payload = format_lark_card(args.title, args.content, None, None)
    send_lark_notification(cli_webhook_url, cli_signing_secret, message_payload)
