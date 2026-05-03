import { UnifiedChatRequest } from "../types/llm";
import { Transformer } from "../types/transformer";

export class OpenAIResponsesTransformer implements Transformer {
  name = "openai-responses";
  endPoint = "/v1/responses";

  async transformRequestIn(
    request: UnifiedChatRequest
  ): Promise<UnifiedChatRequest> {
    delete request.temperature;
    delete request.max_tokens;
    const system = request.messages.filter((msg) => msg.role === "system");
    if (system) {
      if (Array.isArray(system.content)) {
        request.instructions = system.content.join("\n\n");
      } else {
        request.instructions = system.content;
      }
    }
    const input = [];
    request.messages.forEach((message) => {
      if (message.role === "system") return;
      if (Array.isArray(message.content)) {
        message.content.forEach((content) => {
          if (content.type === "text") {
            if (message.role === "assistant") {
              content.type = "output_text";
            } else {
              content.type = "input_text";
            }
          } else if (content.type === "image_url") {
            content.type = "input_image";
            content.image_url = content.image_url.url;
            delete content.media_type;
          }
          delete content.cache_control;
        });
      }
      if (message.role === "tool") {
        message.type = "function_call_output";
        message.call_id = message.tool_call_id;
        message.output = message.content;
        delete message.cache_control;
        delete message.role;
        delete message.tool_call_id;
        delete message.content;
      } else if (message.role === "assistant") {
        if (Array.isArray(message.tool_calls)) {
          message.tool_calls.forEach((tool) => {
            input.push({
              type: "function_call",
              arguments: tool.function.arguments,
              name: tool.function.name,
              call_id: tool.id,
            });
          });
          return;
        }
      }
      input.push(message);
    });
    request.input = input;
    delete request.messages;
    if (Array.isArray(request.tools)) {
      const webSearch = request.tools?.find(
        (tool) => tool.function.name === "web_search"
      );
      request.tools = request.tools.map((tool) => {
        return {
          type: tool.type,
          ...tool.function,
        };
      });
      if (webSearch) {
        request.tools.push({
          type: "web_search_preview"
        });
      }
    }
    return request;
  }

  async transformResponseOut(response: Response): Promise<Response> {
    if (response.headers.get("Content-Type")?.includes("application/json")) {
      const jsonResponse: any = await response.json();

      // Check if this is a responses API format JSON response
      if (jsonResponse.object === "response" && jsonResponse.output) {
        // Convert responses format to chat format
        const chatResponse = this.convertResponseToChat(jsonResponse);
        return new Response(JSON.stringify(chatResponse), {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
      } else {
        // Not responses API format, keep as-is
        return new Response(JSON.stringify(jsonResponse), {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
      }
    } else if (
      response.headers.get("Content-Type")?.includes("text/event-stream")
    ) {
      if (!response.body) {
        return response;
      }

      const decoder = new TextDecoder();
      const encoder = new TextEncoder();
      let buffer = ""; // Buffer for incomplete data
      let currentContent = "";
      let isStreamEnded = false;

      const stream = new ReadableStream({
        async start(controller) {
          const reader = response.body!.getReader();

          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) {
                if (!isStreamEnded) {
                  // Send end marker
                  const doneChunk = `data: [DONE]\n\n`;
                  controller.enqueue(encoder.encode(doneChunk));
                }
                break;
              }

              const chunk = decoder.decode(value, { stream: true });
              buffer += chunk;

              // Process complete data lines in the buffer
              let lines = buffer.split(/\r?\n/);
              buffer = lines.pop() || ""; // Last line may be incomplete, keep in buffer

              for (const line of lines) {
                if (!line.trim()) continue;

                try {
                  if (line.startsWith("event: ")) {
                    // Process event line, store for pairing with next data line
                    continue;
                  } else if (line.startsWith("data: ")) {
                    const dataStr = line.slice(5).trim(); // Remove "data: " prefix
                    if (dataStr === "[DONE]") {
                      isStreamEnded = true;
                      controller.enqueue(encoder.encode(`data: [DONE]\n\n`));
                      continue;
                    }

                    try {
                      const data = JSON.parse(dataStr);

                      // Convert different event types to chat format
                      if (data.type === "response.output_text.delta") {
                        // Convert output_text.delta to chat format
                        currentContent += data.delta || "";

                        const chatChunk = {
                          id: data.item_id || "chatcmpl-" + Date.now(),
                          object: "chat.completion.chunk",
                          created: Math.floor(Date.now() / 1000),
                          model: data.response?.model,
                          choices: [
                            {
                              index: data.output_index || 0,
                              delta: {
                                content: data.delta || "",
                              },
                              finish_reason: null,
                            },
                          ],
                        };

                        controller.enqueue(
                          encoder.encode(
                            `data: ${JSON.stringify(chatChunk)}\n\n`
                          )
                        );
                      } else if (
                        data.type === "response.output_item.added" &&
                        data.item?.type === "function_call"
                      ) {
                        // Handle function call start - create initial tool call chunk
                        const functionCallChunk = {
                          id:
                            data.item.call_id ||
                            data.item.id ||
                            "chatcmpl-" + Date.now(),
                          object: "chat.completion.chunk",
                          created: Math.floor(Date.now() / 1000),
                          model: data.response?.model || "gpt-5-codex-",
                          choices: [
                            {
                              index: data.output_index || 0,
                              delta: {
                                role: "assistant",
                                tool_calls: [
                                  {
                                    index: 0,
                                    id: data.item.call_id || data.item.id,
                                    function: {
                                      name: data.item.name || "",
                                      arguments: "",
                                    },
                                    type: "function",
                                  },
                                ],
                              },
                              finish_reason: null,
                            },
                          ],
                        };

                        controller.enqueue(
                          encoder.encode(
                            `data: ${JSON.stringify(functionCallChunk)}\n\n`
                          )
                        );
                      } else if (
                        data.type === "response.function_call_arguments.delta"
                      ) {
                        // Handle function call argument increments
                        const functionCallChunk = {
                          id: data.item_id || "chatcmpl-" + Date.now(),
                          object: "chat.completion.chunk",
                          created: Math.floor(Date.now() / 1000),
                          model: data.response?.model || "gpt-5-codex-",
                          choices: [
                            {
                              index: data.output_index || 0,
                              delta: {
                                tool_calls: [
                                  {
                                    index: 0,
                                    function: {
                                      arguments: data.delta || "",
                                    },
                                  },
                                ],
                              },
                              finish_reason: null,
                            },
                          ],
                        };

                        controller.enqueue(
                          encoder.encode(
                            `data: ${JSON.stringify(functionCallChunk)}\n\n`
                          )
                        );
                      } else if (data.type === "response.completed") {
                        // Send end marker - check if tool_calls completed
                        const finishReason = data.response?.output?.some(
                          (item: any) => item.type === "function_call"
                        )
                          ? "tool_calls"
                          : "stop";

                        const endChunk = {
                          id: data.response?.id || "chatcmpl-" + Date.now(),
                          object: "chat.completion.chunk",
                          created: Math.floor(Date.now() / 1000),
                          model: data.response?.model || "gpt-5-codex-",
                          choices: [
                            {
                              index: 0,
                              delta: {},
                              finish_reason: finishReason,
                            },
                          ],
                        };

                        controller.enqueue(
                          encoder.encode(
                            `data: ${JSON.stringify(endChunk)}\n\n`
                          )
                        );
                        isStreamEnded = true;
                      } else if (
                        data.type === "response.reasoning_summary_text.delta"
                      ) {
                        // Handle reasoning text (can be skipped or mapped to special format if needed)
                        // For compatibility, we can ignore it or handle as special content
                        continue;
                      }
                      // Other event types are temporarily ignored, only process text content
                    } catch (e) {
                      // If JSON parsing fails, pass through the original line
                      controller.enqueue(encoder.encode(line + "\n"));
                    }
                  } else {
                    // Pass through other lines
                    controller.enqueue(encoder.encode(line + "\n"));
                  }
                } catch (error) {
                  console.error("Error processing line:", line, error);
                  // If parsing fails, pass through the original line
                  controller.enqueue(encoder.encode(line + "\n"));
                }
              }
            }

            // Process remaining data in the buffer
            if (buffer.trim()) {
              controller.enqueue(encoder.encode(buffer + "\n"));
            }

            // Ensure end marker is sent when stream ends
            if (!isStreamEnded) {
              const doneChunk = `data: [DONE]\n\n`;
              controller.enqueue(encoder.encode(doneChunk));
            }
          } catch (error) {
            console.error("Stream error:", error);
            controller.error(error);
          } finally {
            try {
              reader.releaseLock();
            } catch (e) {
              console.error("Error releasing reader lock:", e);
            }
            controller.close();
          }
        },
      });

      return new Response(stream, {
        status: response.status,
        statusText: response.statusText,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    return response;
  }

  private convertResponseToChat(responseData: any): any {
    // Extract different types of outputs from the output array
    const messageOutput = responseData.output?.find(
      (item: any) => item.type === "message"
    );
    const functionCallOutput = responseData.output?.find(
      (item: any) => item.type === "function_call"
    );

    let messageContent = "";
    let toolCalls = null;

    if (messageOutput && messageOutput.content) {
      // Extract text content of output_text type
      const textContent = messageOutput.content
        .filter((item: any) => item.type === "output_text")
        .map((item: any) => item.text)
        .join("");

      messageContent = textContent;
    }

    if (functionCallOutput) {
      // Handle function_call type output
      toolCalls = [
        {
          id: functionCallOutput.call_id || functionCallOutput.id,
          function: {
            name: functionCallOutput.name,
            arguments: functionCallOutput.arguments,
          },
          type: "function",
        },
      ];
    }

    // Build chat format response
    const chatResponse = {
      id: responseData.id || "chatcmpl-" + Date.now(),
      object: "chat.completion",
      created: responseData.created_at,
      model: responseData.model || "gpt-4.1-2025-04-14", // Use appropriate default model name
      choices: [
        {
          index: 0,
          message: {
            role: "assistant",
            content: messageContent || null, // If there are tool_calls, content may be null
            tool_calls: toolCalls,
          },
          logprobs: null,
          finish_reason: toolCalls ? "tool_calls" : "stop",
        },
      ],
      usage: responseData.usage
        ? {
            prompt_tokens: responseData.usage.input_tokens || 0,
            completion_tokens: responseData.usage.output_tokens || 0,
            total_tokens: responseData.usage.total_tokens || 0,
          }
        : null,
    };

    return chatResponse;
  }
}
