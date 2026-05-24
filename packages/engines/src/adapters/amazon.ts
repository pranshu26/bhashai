import { TranslateClient, TranslateTextCommand } from '@aws-sdk/client-translate';
import type { TranslateRequest, TranslateResult, TranslationEngine } from '../types';

export interface AmazonConfig {
  enabled: boolean;
  region: string;
  accessKeyId?: string;
  secretAccessKey?: string;
}

// Indian target languages Amazon Translate supports (Odia/Assamese not supported there).
const AMAZON_TARGETS = new Set(['hi', 'bn', 'gu', 'kn', 'ml', 'mr', 'pa', 'ta', 'te', 'ur']);

export class AmazonTranslateEngine implements TranslationEngine {
  readonly kind = 'AMAZON_TRANSLATE' as const;
  private client: TranslateClient | null = null;

  constructor(private readonly config: AmazonConfig) {}

  isEnabled(): boolean {
    return this.config.enabled;
  }
  supports(src: string, tgt: string): boolean {
    return src === 'en' && AMAZON_TARGETS.has(tgt);
  }

  private getClient(): TranslateClient {
    if (!this.client) {
      this.client = new TranslateClient({
        region: this.config.region,
        credentials:
          this.config.accessKeyId && this.config.secretAccessKey
            ? { accessKeyId: this.config.accessKeyId, secretAccessKey: this.config.secretAccessKey }
            : undefined,
      });
    }
    return this.client;
  }

  async translate(req: TranslateRequest): Promise<TranslateResult> {
    const start = Date.now();
    const res = await this.getClient().send(
      new TranslateTextCommand({
        Text: req.sourceText,
        SourceLanguageCode: req.sourceLanguage,
        TargetLanguageCode: req.targetLanguage,
      }),
    );
    const text = res.TranslatedText ?? '';
    return {
      text,
      raw: text,
      engine: this.kind,
      promptVersion: 'amazon.realtime',
      latencyMs: Date.now() - start,
      costMicroUsd: req.sourceText.length * 15, // ~$15 / 1M chars
    };
  }
}
