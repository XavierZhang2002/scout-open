/**
 * Handle system role messages
 * @param system_message System message content
 * @param context Context information, including request and config
 * @returns Processed system message
 */
function handle_system_message(system_message: string, context?: any): string {
    // Add processing logic for system messages here
    // For example: modify, enhance, filter, etc.

    let processed_message = system_message;

    // Remove specific Claude Code text (multiple variations)
    processed_message = processed_message.replace("You are Claude Code, Anthropic's official CLI for Claude.", "")
    processed_message = processed_message.replace("You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK.", "")

    // Remove Claude agent text (multiple variations)
    processed_message = processed_message.replace("You are a Claude agent, built on Anthropic's Claude Agent SDK.", "")
    processed_message = processed_message.replace("You are a Claude agent, built on Anthropic Claude Agent SDK.", "")

    // Remove any remaining "You are" sentences at the beginning only
    const claude_start_pattern = /^You are.*?\./g
    processed_message = processed_message.replace(claude_start_pattern, '')

    // Remove gitStatus: and everything after it until the end
    const gitstatus_pattern = /gitStatus:.*$/gs
    processed_message = processed_message.replace(gitstatus_pattern, '')

    // Remove <system-reminder> ... </system-reminder> blocks including the markers (multiline)
    const reminder_pattern = /<system-reminder>.*?<\/system-reminder>/gs
    processed_message = processed_message.replace(reminder_pattern, '')

    // Clean up extra whitespace
    processed_message = processed_message.replace(/\n\s*\n/g, '\n').trim()

    return processed_message;
}

/**
 * Handle user role messages
 * @param user_message User message content
 * @param context Context information, including request and config
 * @returns Processed user message
 */
function handle_user_message(user_message: string, context?: any): string {
    // Add processing logic for user messages here
    // For example: modify, enhance, filter, etc.

    let processed_message = user_message;

    // Remove <system-reminder> ... </system-reminder> blocks including the markers (multiline)
    const reminder_pattern = /<system-reminder>.*?<\/system-reminder>/gs
    processed_message = processed_message.replace(reminder_pattern, '')

    // Clean up extra whitespace
    processed_message = processed_message.replace(/\n\s*\n/g, '\n').trim()

    return processed_message;
}

/**
 * Handle tool role messages
 * @param tool_content Tool message content
 * @param context Context information, including request and config
 * @returns Processed tool message content
 */
function handle_tool_message(tool_content: string, context?: any): string {
    console.log('[TOOL_HOOK] Original tool_content:', tool_content);
    console.log('[TOOL_HOOK] tool_content type:', typeof tool_content);
    
    // Try to parse JSON format content
    try {
        const parsed = JSON.parse(tool_content);
        console.log('[TOOL_HOOK] Parsed JSON:', JSON.stringify(parsed, null, 2));
        console.log('[TOOL_HOOK] Is array:', Array.isArray(parsed));

        // If the parsed result is an array with elements
        if (Array.isArray(parsed) && parsed.length > 0) {
            const firstElement = parsed[0];
            console.log('[TOOL_HOOK] First element:', JSON.stringify(firstElement, null, 2));

            // If the first element has a text field, return the text content
            if (firstElement && firstElement.text) {
                console.log('[TOOL_HOOK] Extracted text:', firstElement.text);
                return firstElement.text;
            }
        }
    } catch (e) {
        // JSON parsing failed, return original content
        console.log('[TOOL_HOOK] JSON parse error:', e);
    }
    
    console.log('[TOOL_HOOK] Returning original content');
    return tool_content;
}

/**
 * Process message array, applying corresponding hook functions
 * @param messages Message array
 * @param context Context information
 * @returns Processed message array
 */
function process_messages(messages: any[], context?: any) {
    console.log('[HOOK] process_messages called, messages count:', Array.isArray(messages) ? messages.length : 'not array');

    if (!Array.isArray(messages)) {
        return messages;
    }

    return messages.map((message, index) => {
        console.log(`[HOOK] Processing message ${index}, role:`, message?.role);

        if (!message || typeof message !== 'object' || !message.role) {
            return message;
        }

        switch (message.role) {
            case 'system':
                if (typeof message.content === 'string') {
                    const processedContent = handle_system_message(message.content, context);
                    return {
                        ...message,
                        content: processedContent
                    };
                } else if (Array.isArray(message.content)) {
                    // Handle complex content formats (e.g., containing text and images)
                    return {
                        ...message,
                        content: message.content.map((item: any) => {
                            if (item.type === 'text' && typeof item.text === 'string') {
                                return {
                                    ...item,
                                    text: handle_system_message(item.text, context)
                                };
                            }
                            return item;
                        })
                    };
                }
                break;

            case 'user':
                if (typeof message.content === 'string') {
                    return {
                        ...message,
                        content: handle_user_message(message.content, context)
                    };
                } else if (Array.isArray(message.content)) {
                    // Handle complex content formats (e.g., containing text and images)
                    return {
                        ...message,
                        content: message.content.map((item: any) => {
                            // Handle tool_result type
                            if (item.type === 'tool_result' && Array.isArray(item.content)) {
                                console.log('[TOOL_RESULT_HOOK] Found tool_result');
                                console.log('[TOOL_RESULT_HOOK] Original item:', JSON.stringify(item, null, 2));
                                
                                // Extract the text from the first element
                                if (item.content.length > 0 && item.content[0].text) {
                                    const extractedText = item.content[0].text;
                                    console.log('[TOOL_RESULT_HOOK] Extracted text:', extractedText);
                                    
                                    return {
                                        ...item,
                                        content: extractedText
                                    };
                                }
                            }
                            // Handle regular text
                            else if (item.type === 'text' && typeof item.text === 'string') {
                                return {
                                    ...item,
                                    text: handle_user_message(item.text, context)
                                };
                            }
                            return item;
                        })
                    };
                }
                break;

            case 'tool':
                console.log('[TOOL_HOOK] Processing tool message');
                console.log('[TOOL_HOOK] Message:', JSON.stringify(message, null, 2));
                if (typeof message.content === 'string') {
                    const processedContent = handle_tool_message(message.content, context);
                    console.log('[TOOL_HOOK] Processed content:', processedContent);
                    return {
                        ...message,
                        content: processedContent
                    };
                } else {
                    console.log('[TOOL_HOOK] Content is not string, type:', typeof message.content);
                }
                break;

            default:
                // For other roles (e.g., assistant), do not process
                return message;
        }

        return message;
    });
}

// Export functions
export {
    handle_system_message,
    handle_user_message,
    handle_tool_message,
    process_messages
};
