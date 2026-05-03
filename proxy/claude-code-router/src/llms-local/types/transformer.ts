import { LLMProvider, UnifiedChatRequest } from "./llm";

export interface TransformerOptions {
  [key: string]: any;
}

interface TransformerWithStaticName {
  new (options?: TransformerOptions): Transformer;
  TransformerName?: string;
}


interface TransformerWithInstanceName {
  new (): Transformer;
  name?: never;
}

export type TransformerConstructor = TransformerWithStaticName;

export interface TransformerContext {
  [key: string]: any;
}

export type Transformer = {
  transformRequestIn?: (
    request: UnifiedChatRequest,
    provider: LLMProvider,
    context: TransformerContext,
  ) => Promise<Record<string, any>>;
  transformResponseIn?: (response: Response, context?: TransformerContext) => Promise<Response>;

  // Convert request format to unified format
  transformRequestOut?: (request: any, context: TransformerContext) => Promise<UnifiedChatRequest>;
  // Convert response format to unified format
  transformResponseOut?: (response: Response, context: TransformerContext) => Promise<Response>;

  endPoint?: string;
  name?: string;
  auth?: (request: any, provider: LLMProvider, context: TransformerContext) => Promise<any>;
  
  // Logger for transformer
  logger?: any;
};
