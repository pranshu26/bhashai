export interface LlmMessage {
  system: string;
  user: string;
}
export interface LlmResult {
  text: string;
  inputTokens?: number;
  outputTokens?: number;
}
export interface LlmCompleteOpts {
  maxTokens?: number;
  temperature?: number;
}
export interface LlmProvider {
  readonly name: string;
  complete(msg: LlmMessage, opts?: LlmCompleteOpts): Promise<LlmResult>;
}

export interface LlmConfig {
  provider: 'anthropic' | 'openai' | 'gemini';
  apiKey: string;
  model?: string;
}

class AnthropicProvider implements LlmProvider {
  readonly name = 'anthropic';
  constructor(
    private readonly apiKey: string,
    private readonly model = 'claude-sonnet-4-6',
  ) {}
  async complete(msg: LlmMessage, opts: LlmCompleteOpts = {}): Promise<LlmResult> {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: opts.maxTokens ?? 4096,
        temperature: opts.temperature ?? 0.2,
        system: msg.system,
        messages: [{ role: 'user', content: msg.user }],
      }),
    });
    if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as {
      content: Array<{ type: string; text?: string }>;
      usage?: { input_tokens: number; output_tokens: number };
    };
    const text = data.content.find((c) => c.type === 'text')?.text ?? '';
    return { text, inputTokens: data.usage?.input_tokens, outputTokens: data.usage?.output_tokens };
  }
}

class OpenAiProvider implements LlmProvider {
  readonly name = 'openai';
  constructor(
    private readonly apiKey: string,
    private readonly model = 'gpt-4o',
  ) {}
  async complete(msg: LlmMessage, opts: LlmCompleteOpts = {}): Promise<LlmResult> {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { authorization: `Bearer ${this.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        model: this.model,
        temperature: opts.temperature ?? 0.2,
        max_tokens: opts.maxTokens ?? 4096,
        messages: [
          { role: 'system', content: msg.system },
          { role: 'user', content: msg.user },
        ],
      }),
    });
    if (!res.ok) throw new Error(`OpenAI ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as {
      choices: Array<{ message: { content: string } }>;
      usage?: { prompt_tokens: number; completion_tokens: number };
    };
    return {
      text: data.choices[0]?.message.content ?? '',
      inputTokens: data.usage?.prompt_tokens,
      outputTokens: data.usage?.completion_tokens,
    };
  }
}

export function createLlmProvider(config: LlmConfig): LlmProvider {
  switch (config.provider) {
    case 'anthropic':
      return new AnthropicProvider(config.apiKey, config.model);
    case 'openai':
    case 'gemini': // gemini adapter TODO (Phase 3); fall back to OpenAI-compatible shape
      return new OpenAiProvider(config.apiKey, config.model);
    default:
      throw new Error(`Unknown LLM provider: ${config.provider}`);
  }
}

/** Rough cost estimate in micro-USD (default Sonnet-ish pricing: $3/$15 per MTok). */
export function estimateCostMicroUsd(
  inputTokens = 0,
  outputTokens = 0,
  inPerMTok = 3,
  outPerMTok = 15,
): number {
  return Math.round(inputTokens * inPerMTok + outputTokens * outPerMTok);
}
