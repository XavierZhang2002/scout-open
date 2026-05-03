#!/bin/sh

# Use supervisord to manage all processes, ensuring the container doesn't exit due to claude-code-router restart
reload_supervisord_config() {
    # Run supervisord directly (not in background)
    echo "Starting supervisord with claude-code-router..."
    exec supervisord -c /etc/supervisor/conf.d/supervisord.conf -n
}

# Main execution logic
reload_supervisord_config