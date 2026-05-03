/**
 * Hook utilities for message processing
 * Hook functions for processing system and user messages
 */

export interface HookContext {
  req?: any;
  transformer?: any;
  provider?: any;
  [key: string]: any;
}

/**
 * Handle system role messages
 * @param system_message System message content
 * @param context Context information
 * @returns Processed system message
 */
export function handleSystemMessage(system_message: string, context?: HookContext): string {
    // Add processing logic for system messages here
    // For example: modify, enhance, filter, etc.

    let processed_message = system_message;

    // Example: check or modify system message content
    // if (system_message.includes('specific_keyword')) {
    //     processed_message = system_message.replace('specific_keyword', 'replacement');
    // }

    // Example: add specific prefix or suffix
    // processed_message = `[Enhanced System Instructions]\n${system_message}`;

    // By default, return the original message (no modification)
    return processed_message;
}

/**
 * Handle user role messages
 * @param user_message User message content
 * @param context Context information
 * @returns Processed user message
 */
export function handleUserMessage(user_message: string, context?: HookContext): string {
    // Add processing logic for user messages here
    // For example: modify, enhance, filter, etc.

    let processed_message = user_message;

    // Example: check or modify user message content
    // if (user_message.includes('forbidden_content')) {
    //     processed_message = 'I cannot process this type of request.';
    // }

    // Example: add specific processing logic
    // processed_message = `[Enhanced User Request]\n${user_message}`;

    // By default, return the original message (no modification)
    return processed_message;
}

/**
 * Process message array, applying corresponding hook functions
 * @param messages Message array
 * @param context Context information
 * @returns Processed message array
 */
export function processMessages(messages: any[], context?: HookContext): any[] {
    if (!Array.isArray(messages)) {
        return messages;
    }

    return messages.map(message => {
        if (!message || typeof message !== 'object' || !message.role) {
            return message;
        }

        switch (message.role) {
            case 'system':
                if (typeof message.content === 'string') {
                    return {
                        ...message,
                        content: handleSystemMessage(message.content, context)
                    };
                } else if (Array.isArray(message.content)) {
                    // Handle complex content formats (e.g., containing text and images)
                    return {
                        ...message,
                        content: message.content.map((item: any) => {
                            if (item.type === 'text' && typeof item.text === 'string') {
                                return {
                                    ...item,
                                    text: handleSystemMessage(item.text, context)
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
                        content: handleUserMessage(message.content, context)
                    };
                } else if (Array.isArray(message.content)) {
                    // Handle complex content formats (e.g., containing text and images)
                    return {
                        ...message,
                        content: message.content.map((item: any) => {
                            if (item.type === 'text' && typeof item.text === 'string') {
                                return {
                                    ...item,
                                    text: handleUserMessage(item.text, context)
                                };
                            }
                            return item;
                        })
                    };
                }
                break;

            default:
                // For other roles (e.g., assistant), do not process
                return message;
        }

        return message;
    });
}