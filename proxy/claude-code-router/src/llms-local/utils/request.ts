import { ProxyAgent } from "undici";
import { UnifiedChatRequest } from "../types/llm";

export function sendUnifiedRequest(
  url: URL | string,
  request: UnifiedChatRequest,
  config: any,
  context: any,
  logger?: any
): Promise<Response> {
  const headers = new Headers({
    "Content-Type": "application/json",
  });
  if (config.headers) {
    Object.entries(config.headers).forEach(([key, value]) => {
      if (value) {
        headers.set(key, value as string);
      }
    });
  }
  let combinedSignal: AbortSignal;
  const timeoutSignal = AbortSignal.timeout(config.TIMEOUT ?? 60 * 1000 * 60);

  if (config.signal) {
    const controller = new AbortController();
    const abortHandler = () => controller.abort();
    config.signal.addEventListener("abort", abortHandler);
    timeoutSignal.addEventListener("abort", abortHandler);
    combinedSignal = controller.signal;
  } else {
    combinedSignal = timeoutSignal;
  }

  const requestBody = JSON.stringify(request);
  
  const fetchOptions: RequestInit = {
    method: "POST",
    headers: headers,
    body: requestBody,
    signal: combinedSignal,
  };

  if (config.httpsProxy) {
    (fetchOptions as any).dispatcher = new ProxyAgent(
      new URL(config.httpsProxy).toString()
    );
  }
  
  const requestUrl = typeof url === "string" ? url : url.toString();
  
  // Extract first and last 100 characters of messages
  const getMessagesSummary = (messages: any[]) => {
    if (!messages || messages.length === 0) {
      return { first100: '', last100: '' };
    }
    
    const messagesStr = JSON.stringify(messages);
    const first100 = messagesStr.substring(0, 100);
    const last100 = messagesStr.length > 100 
      ? messagesStr.substring(messagesStr.length - 100) 
      : messagesStr;
    
    return { first100, last100 };
  };
  
  const messagesSummary = getMessagesSummary(request.messages);
  
  logger?.debug(
    {
      reqId: context.req.id,
      request: fetchOptions,
      headers: Object.fromEntries(headers.entries()),
      requestUrl: requestUrl,
      useProxy: config.httpsProxy,
    },
    "final request"
  );
  
  // Send request and log response
  return fetch(requestUrl, fetchOptions).then(async (response) => {
    // Log basic response information
    const responseHeaders = Object.fromEntries(response.headers.entries());
    const isStream = responseHeaders['content-type']?.includes('stream');

    // Log response information
    if (!isStream) {
      // Non-streaming response: read full response body
      try {
        // Clone response for reading
        const clonedResponse = response.clone();
        const responseText = await clonedResponse.text();
        let responseParsed;
        try {
          responseParsed = JSON.parse(responseText);
        } catch {
          responseParsed = responseText;
        }
        
        logger?.info(
          {
            reqId: context.req.id,
            // Request information
            requestModel: request.model,
            requestProvider: context.req.provider,
            requestHasTools: !!request.tools && request.tools.length > 0,
            requestToolCount: request.tools?.length || 0,
            requestMaxTokens: request.max_tokens,
            requestTemperature: request.temperature,
            requestParsed: request,
            responseBodyParsed: responseParsed,
          },
          "=== LLM response received === messages summary: " + messagesSummary.first100 + "..." + messagesSummary.last100
        );
      } catch (error: any) {
        logger?.error(
          {
            reqId: context.req.id,
            requestModel: request.model,
            requestProvider: context.req.provider,
            requestMessageCount: request.messages?.length || 0,
            requestMessagesFirst100: messagesSummary.first100,
            requestMessagesLast100: messagesSummary.last100,
            error: error.message,
            stack: error.stack,
          },
          "Error logging LLM response"
        );
      }
    } else {
      // Streaming response: intercept stream data for logging
      try {
        const originalBody = response.body;
        if (!originalBody) {
          return response;
        }

        let streamedData = '';
        const chunks: string[] = [];
        
        // Create a TransformStream to intercept data
        const transformStream = new TransformStream({
          transform(chunk, controller) {
            // Pass chunk to downstream
            controller.enqueue(chunk);

            // Also collect data for logging
            try {
              const text = new TextDecoder().decode(chunk);
              chunks.push(text);
              streamedData += text;
            } catch (e) {
              // Ignore decoding errors
            }
          },
          flush() {
            // Log complete response data when stream ends
            try {
              // Parse all chunks and combine into complete response format
              let combinedContent = '';
              let role = 'assistant';
              let finishReason = null;
              let firstChunk: any = null;
              let usage: any = null;
              
              chunks.forEach(chunk => {
                const lines = chunk.split('\n').filter(line => line.trim().startsWith('data:'));
                lines.forEach(line => {
                  try {
                    const jsonStr = line.replace(/^data:\s*/, '');
                    if (jsonStr.trim() && jsonStr.trim() !== '[DONE]') {
                      const parsed = JSON.parse(jsonStr);
                      
                      // Save first chunk for getting id, model and other info
                      if (!firstChunk) {
                        firstChunk = parsed;
                      }
                      
                      const choice = parsed.choices?.[0];
                      if (choice) {
                        const delta = choice.delta;
                        
                        // Extract role
                        if (delta?.role) {
                          role = delta.role;
                        }
                        
                        // Extract content
                        if (delta?.content) {
                          combinedContent += delta.content;
                        }
                        
                        // Extract finish_reason
                        if (choice.finish_reason) {
                          finishReason = choice.finish_reason;
                        }
                      }
                      
                      // Extract usage (usually in the last chunk)
                      if (parsed.usage) {
                        usage = parsed.usage;
                      }
                    }
                  } catch (e) {
                    // Ignore parsing errors
                  }
                });
              });

              // Build response object in the same format as non-streaming response
              const completionResponse: any = {
                id: firstChunk?.id || '',
                object: 'chat.completion',
                created: firstChunk?.created || Math.floor(Date.now() / 1000),
                model: firstChunk?.model || request.model,
                choices: [
                  {
                    index: 0,
                    message: {
                      role: role,
                      content: combinedContent || null,
                    },
                    finish_reason: finishReason
                  }
                ]
              };
              
              // If usage is present, add to response
              if (usage) {
                completionResponse.usage = usage;
              }
              
              // If venusMarker is present, add to response
              if (firstChunk?.venusMarker) {
                completionResponse.venusMarker = firstChunk.venusMarker;
              }

              logger?.info(
                {
                  reqId: context.req.id,
                  // 请求信息
                  requestModel: request.model,
                  requestProvider: context.req.provider,
                  requestHasTools: !!request.tools && request.tools.length > 0,
                  requestToolCount: request.tools?.length || 0,
                  requestMaxTokens: request.max_tokens,
                  requestTemperature: request.temperature,
                  requestParsed: request,
                  // Response information - same format as non-streaming
                  responseBodyParsed: completionResponse,
                },
                "=== LLM response received === messages summary: " + messagesSummary.first100 + "..." + messagesSummary.last100
              );
            } catch (error: any) {
              logger?.error(
                {
                  reqId: context.req.id,
                  requestModel: request.model,
                  requestProvider: context.req.provider,
                  requestMessageCount: request.messages?.length || 0,
                  requestMessagesFirst100: messagesSummary.first100,
                  requestMessagesLast100: messagesSummary.last100,
                  error: error.message,
                  stack: error.stack,
                },
                "Error logging LLM response"
              );
            }
          }
        });

        // Create new response using the intercepted stream
        const newResponse = new Response(
          originalBody.pipeThrough(transformStream),
          {
            status: response.status,
            statusText: response.statusText,
            headers: response.headers,
          }
        );

        return newResponse;
      } catch (error: any) {
        logger?.error(
          {
            reqId: context.req.id,
            requestModel: request.model,
            requestProvider: context.req.provider,
            requestMessageCount: request.messages?.length || 0,
            requestMessagesFirst100: messagesSummary.first100,
            requestMessagesLast100: messagesSummary.last100,
            error: error.message,
            stack: error.stack,
          },
          "Error setting up stream logging"
        );
        return response;
      }
    }
    
    return response;
  }).catch((error) => {
    // Log request errors
    logger?.error(
      {
        reqId: context.req.id,
        requestUrl: requestUrl,
        requestModel: request.model,
        requestProvider: context.req.provider,
        requestMessageCount: request.messages?.length || 0,
        requestMessagesFirst100: messagesSummary.first100,
        requestMessagesLast100: messagesSummary.last100,
        requestHasTools: !!request.tools && request.tools.length > 0,
        requestToolCount: request.tools?.length || 0,
        error: error.message,
        errorName: error.name,
        errorCode: error.code,
        stack: error.stack,
      },
      "=== LLM request failed ==="
    );
    throw error;
  });
}
