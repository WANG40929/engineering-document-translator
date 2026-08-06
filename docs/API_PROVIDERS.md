# API 供应商配置 / API Provider Setup

文档智能翻译器 v1.5.0 不再绑定单一模型服务。设置页可以保存多个服务配置，每个配置包含供应商、接口地址、模型或部署名称，以及独立加密的 API Key。

Document Translator v1.5.0 is no longer tied to one model service. Settings can store multiple profiles, each with its provider, endpoint, model or deployment name, and a separately encrypted API key.

## 内置预设 / Built-in presets

| 类别 / Type | 服务 / Services | 协议 / Protocol |
|---|---|---|
| 国际服务 | OpenAI、Anthropic Claude、Google Gemini、Azure OpenAI、Mistral、Groq、Together AI、OpenRouter | OpenAI-compatible、Anthropic Messages 或 Azure OpenAI |
| 中国服务 | DeepSeek、阿里云百炼/Qwen、Moonshot/Kimi、智谱 GLM、火山方舟/豆包、SiliconFlow | 主要为 OpenAI-compatible |
| 本地服务 | Ollama、LM Studio、vLLM | OpenAI-compatible；默认不要求 API Key |
| 自定义 | 任意兼容 OpenAI Chat Completions 的接口 | OpenAI-compatible |

预设地址只是便捷初始值，接口地址和模型均可修改。服务商调整模型名称后，可点击“测试连接并获取模型”，或直接手动填写新模型名。

Preset endpoints are editable defaults. If a provider changes its model catalog, use **Test connection and load models** or enter a model ID manually.

## 推荐设置流程 / Recommended setup

1. 在“设置 → 翻译设置”中新建或选择服务配置。
2. 选择供应商，核对接口地址并填写模型。
3. 填写该服务的 API Key；本地服务通常可留空。
4. 点击“测试连接并获取模型”。测试可能产生极少量 token，因为部分服务不提供模型列表接口。
5. 如需容灾，再建立第二个配置，并把它选为“故障备用服务”。

API Key 由服务商提供，软件不附带任何密钥。保存密钥时使用当前 Windows 用户的 DPAPI 加密；不同 Windows 用户不能直接解密。

API keys come from the selected provider and are not bundled. Saved keys use Windows DPAPI and can only be decrypted by the same Windows user account.

## Azure OpenAI

Azure OpenAI 的“接口地址”应填写完整部署地址，例如：

```text
https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT/chat/completions
```

软件会附加 `api-version` 并使用 `api-key` 请求头。“模型 / 部署名称”用于界面和缓存隔离；实际部署由 URL 决定。如果地址已经包含 `api-version`，软件会保留它。

## 智能 PDF 限制 / Smart PDF limitation

BabelDOC 智能 PDF 后端目前接收 OpenAI-compatible 配置。OpenAI-compatible、Azure 和多数内置预设可直接使用。Anthropic 原生 Messages API 不能直接交给 BabelDOC；请配置一个 OpenAI-compatible 备用服务，或改用“原位保版”。如果智能 PDF 后端失败，v1.5.0 会尝试用原位保版完成文档，并在报告中记录警告。

BabelDOC smart PDF currently accepts OpenAI-compatible configuration. Native Anthropic Messages cannot be passed to BabelDOC directly; configure an OpenAI-compatible fallback or use strict in-place mode. If smart PDF processing fails, v1.5.0 attempts strict placement and records a warning.

## 缓存、token 与费用 / Cache, tokens, and pricing

- 缓存会按供应商、协议、接口地址、模型、语言和质量设置隔离。
- 软件记录 API 响应实际返回的输入、输出和总 token；服务商没有返回的项目不会猜测。
- 软件不内置单价，也不显示预计费用。价格、缓存折扣、区域和套餐变化由服务商账单为准。

- Cache entries are isolated by provider, protocol, endpoint, model, language, and quality settings.
- Token counters use actual values returned by the API; missing values are not guessed.
- The application does not embed prices or estimate charges. Provider billing is authoritative.

## 官方接口资料 / Official API references

- [DeepSeek API](https://api-docs.deepseek.com/)
- [OpenAI API](https://platform.openai.com/docs/api-reference)
- [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Alibaba Model Studio endpoints](https://help.aliyun.com/en/model-studio/base-url)
- [Azure OpenAI REST API](https://learn.microsoft.com/azure/ai-services/openai/reference)

