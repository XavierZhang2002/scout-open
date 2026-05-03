# Scout Proxy — Claude Code Router

## Overview

Claude Code Router (CCR) is an API proxy/gateway that bridges the Claude Agent SDK and actual LLM Providers.

**Core function**: Translates Anthropic Messages API (`/v1/messages`) requests into formats that various LLM Providers (OpenAI, DeepSeek, vLLM, etc.) can understand, and converts responses back to Anthropic format.

## Architecture

```
Scout Agent (Claude Agent SDK)
    |
    |  POST /v1/messages (Anthropic format, streaming SSE)
    v
Claude Code Router (localhost:3456)
    |
    |  1. Parse model field: "provider,model_name"
    |  2. Request transform: Anthropic -> OpenAI/other format
    |  3. Forward to corresponding Provider
    |  4. Response transform: OpenAI/other format -> Anthropic SSE
    v
LLM Provider (DeepSeek / vLLM / OpenRouter / Azure / Vertex / ...)
```

## Model Routing Format

In Scout, the `model` field encodes routing information:

```
"provider_name,model_name"
```

Examples:
- `"venus,deepseek-v3.1-terminus"` — Route to Venus platform for DeepSeek V3.1
- `"openrouter,anthropic/claude-sonnet-4.5"` — Route via OpenRouter for Claude
- `"vllm,Qwen_Qwen3-30B-A3B-Instruct-2507"` — Route to self-hosted vLLM
- `"ds,deepseek-chat"` — Route to DeepSeek API directly
- `"azure,gpt-5"` — Route to Azure OpenAI

## Quick Start

### Deploy CCR

```bash
cd proxy
bash deploy.bash
```

### Check Status

```bash
bash status.bash
```

### Stop Service

```bash
bash stop.bash
```

### Use with Scout

In `config.yaml` at the project root:
```yaml
api:
  base_url: "http://localhost:3456"
  auth_token: "wink"
  model: "venus,deepseek-v3.1-terminus"
```

## Configuration

CCR configuration is in `.claude-code-router/config.json`. Copy the template:

```bash
cp .claude-code-router/config.example.json .claude-code-router/config.json
vim .claude-code-router/config.json
```

The config file is copied to `~/.claude-code-router/config.json` during deployment.

### Config Structure

```json
{
  "HOST": "0.0.0.0",
  "APIKEY": "wink",
  "LOG": true,
  "Providers": [...],
  "Router": {
    "default": "venus,deepseek-v3.1-terminus"
  }
}
```

### Provider Configuration

Each Provider requires:
- `name` — Prefix name used in the model field
- `api_base_url` — Backend API endpoint
- `api_key` — API key
- `models` — List of supported models
- `transformer.use` — Transformer pipeline to use

### Available Transformers

| Transformer | Purpose |
|-------------|---------|
| `openai` | Standard OpenAI Chat Completions format |
| `openrouter` | OpenRouter compatible format |
| `deepseek` | DeepSeek specific format (reasoning) |
| `tooluse` | DeepSeek tool_use adaptation |
| `maxtoken` | Limit max_tokens |
| `sampling` | Set temperature |
| `vertex-claude` | Vertex AI Claude format |
| `vertex-gemini` | Vertex AI Gemini format |
| `maxcompletiontokens` | Azure format (max_completion_tokens) |

## Directory Structure

```
proxy/
├── deploy.bash                    # One-click deploy script
├── stop.bash                      # Stop service script
├── status.bash                    # Health check script
├── .claude-code-router/
│   └── config.example.json        # Config template
├── claude-code-router/            # CCR source code
│   ├── src/
│   │   ├── main.ts                # Entry point (pnpm run front)
│   │   ├── server.ts              # Fastify server + API routes
│   │   └── llms-local/
│   │       ├── server.ts          # Core Server class
│   │       ├── api/routes.ts      # API routes and Transformer dispatch
│   │       ├── transformer/       # Provider Transformers
│   │       └── services/
│   ├── package.json
│   └── pnpm-lock.yaml
├── Dockerfile                     # Docker build (optional)
├── docker-compose.yml             # Docker Compose (optional)
├── docker-entrypoint.sh
└── supervisord.conf
```

## Notes

- **Sensitive data**: `config.json` contains API keys — excluded from git via `.gitignore`
- **Port**: Default 3456, configurable in config.json
- **Node.js**: Requires Node.js 18+ and pnpm
- **Logs**: Real-time logs at `log/ccr.log`, view with `tail -f log/ccr.log`
