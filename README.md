# App Store Connect Webhook 转发器 (至飞书 / Lark)

这是一个基于 Google Cloud Functions 的无服务器（Serverless）应用，
用于接收来自 App Store Connect 的 Webhook 通知，
并将其格式化为内容丰富的卡片消息，安全地转发到指定的飞书 (Feishu) 或 Lark 群组中。

当您的 App 在 App Store Connect 中的状态发生变化时（例如：版本状态更新、收到新的 TestFlight 反馈等），
您和您的团队可以在飞书或 Lark 中立即收到通知。

## ✨ 主要特性

* **🚀 无服务器架构**: 基于 Google Cloud Functions 部署，无需购买和维护服务器，成本极低，具备高可用性和自动扩缩容能力。
* **🔐 双向安全验证**:
    * 验证来自 App Store Connect 的请求签名，确保消息来源可信。
    * 向飞书 / Lark 发送消息时进行签名，防止 Webhook URL 被滥用。
* **🎨 丰富的消息格式**: 将不同类型的通知（如版本状态、构建状态、TestFlight 反馈）解析并格式化为美观且易于阅读的卡片消息。
* **📱 支持多应用**: 单个云函数实例可以接收并处理来自您账户下多个不同 App 的通知，并在消息中自动区分。
* **🐍 易于部署与定制**: 使用 Python 编写，代码逻辑清晰，仅需一条 gcloud 命令即可完成部署，并可轻松自定义消息卡片样式。
* **🔄 持续集成/持续部署**: 支持通过 GitHub Actions 实现自动化部署，push 代码即可自动更新云函数。

## 🛠️ 部署指南

以下为手动部署的步骤。如果您希望配置自动化部署，请参考下一章节。

### 第 1 步：在飞书 / Lark 中创建机器人

1. 在飞书或 Lark 中选择一个您想接收通知的群组。
2. 进入群组 **设置 -> 群机器人 -> 添加机器人**。
3. 选择 **“自定义机器人”**。
4. 为机器人设置一个名称（例如：“App Store 通知”）和描述。
5. （可选）在“安全设置”中，选择 **“签名校验”**。
6. 点击“添加”后，您会得到两个关键信息，请务必复制并保存好：
    * **Webhook 地址**
    * （可选）**签名密钥 (Signing Key)**

### 第 2 步：部署云函数

**前提条件:**

* 拥有一个 Google Cloud Platform (GCP) 账号，并已创建好项目。
* 在本地安装并配置好了 gcloud 命令行工具。
* 已为您的 GCP 项目[开通 Cloud Functions API](https://console.cloud.google.com/apis/library/cloudfunctions.googleapis.com)。

**部署操作:**

1. 将 main.py 和 requirements.txt 文件保存在本地同一个文件夹中。
2. 打开终端，进入该文件夹。
3. 执行以下部署命令：

```
gcloud functions deploy app-store-webhook-forwarder \
--runtime python39 \
--trigger-http \
--allow-unauthenticated \
--entry-point webhook_handler \
--set-env-vars LARK_WEBHOOK_URL="您获取的Webhook地址",LARK_SIGNING_SECRET="您获取的机器人签名密钥",APP_STORE_CONNECT_SECRET="您设定的一个随机密钥"
```

**请务必替换命令中的三个参数**：

* LARK_WEBHOOK_URL: 替换为第 1 步中获取的 **Webhook 地址**。
* LARK_SIGNING_SECRET: （可选）替换为第 1 步中获取的 **签名密钥**。
* APP_STORE_CONNECT_SECRET: **创建一个您自己的、足够复杂的随机字符串**作为密钥（例如，通过 openssl rand -hex 32 生成）。
  这个密钥将用于 App Store Connect 和云函数之间的通信。

部署成功后，GCP 会返回一个 **HTTPS 触发器 URL**。请复制并保存这个 URL。

### 第 3 步：在 App Store Connect 中配置 Webhook

1. 登录 [App Store Connect](https://appstoreconnect.apple.com/)。
2. 导航至 **用户和访问 -> 集成** 标签页。
3. 在左侧边栏选择 **Webhooks**，然后点击 **“+”** 添加。
4. 填写配置信息：
    * **名称 (Name)**: 填写一个方便识别的名称（例如：“Notifier”）。
    * **URL**: 粘贴您在第 2 步中部署云函数后得到的 **HTTPS 触发器 URL**。
    * **密钥 (Secret)**: 粘贴您在第 2 步中为 APP_STORE_CONNECT_SECRET 设定的那个**随机密钥**。
    * **事件 (Events)**: 选择您希望监听的所有事件类型。
5. 点击“创建”。App Store Connect 会立即发送一个测试请求，您可以在群组中查看是否收到了测试通知。

## 🚀 (可选) 自动化部署 (CI/CD)

您可以配置 GitHub Actions，实现在代码推送到 main 分支时自动部署或更新您的 Google Cloud Function。

### 第 1 步：获取 GCP 服务账号密钥

为了让 GitHub Actions 有权限操作您的 GCP 资源，您需要创建一个服务账号并获取其 JSON 密钥。

* **请参考 [如何获取 GCP 服务账号密钥](https://www.google.com/search?q=gcp_service_account_key_guide.md) 这份详细指南完成操作。**

### 第 2 步：在 GitHub 仓库中配置 Secrets

将您的密钥和配置信息安全地存储在 GitHub 的 Secrets 中。

1. 打开您的 GitHub 仓库页面，进入 **Settings** > **Secrets and variables** > **Actions**。
2. 点击 **“New repository secret”** 按钮，依次添加以下四个 Secrets：
   * GCP_PROJECT_ID: 您的 GCP 项目 ID。
   * GCP_SA_EMAIL: 您创建的服务账号的完整邮箱地址。
   * WIF_PROVIDER: 您的 Workload Identity Provider 路径。
   * LARK_WEBHOOK_URL: 您的飞书 / Lark 机器人 Webhook 地址。
   * LARK_SIGNING_SECRET: （可选）您的飞书 / Lark 机器人签名密钥。
   * APP_STORE_CONNECT_SECRET: 您为 App Store Connect Webhook 设定的共享密钥。

### 第 3 步：创建 GitHub Action 工作流

1. 在您的项目根目录下，创建一个 .github/workflows 文件夹。
2. 在该文件夹中，创建一个名为 deploy.yml 的文件。
3. 参考已有的文件进行设置：[deploy.yaml](.github/workflows/deploy.yml)

配置完成后，每当您向 main 分支推送代码时，
GitHub Actions 就会自动将最新的代码部署到您的
Google Cloud Function，无需任何手动操作。

## ⚙️ 环境变量

本函数通过环境变量进行配置，以确保密钥等敏感信息的安全。

| 环境变量                     | 作用                           | 是否必须 |
|--------------------------|------------------------------|------|
| LARK_WEBHOOK_URL         | 飞书 / Lark 自定义机器Webhook 地址。   | 是    |
| LARK_SIGNING_SECRET      | 用于对发送到飞书 / Lark 的消息进行签名。     | 否    |
| APP_STORE_CONNECT_SECRET | 用于验证 App Store Connect 请求签名。 | 是    |

## 🎨 自定义

如果您想修改飞书 / Lark 卡片消息的样式或内容，
可以直接编辑 main.py 文件中的 format_lark_card 函数。
您可以根据 App Store Connect 发送的 JSON 数据，自由地增删字段或调整卡片布局。

## 📄 许可证

本项目采用 [MIT License](https://opensource.org/licenses/MIT) 授权。
