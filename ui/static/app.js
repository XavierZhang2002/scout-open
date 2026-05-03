/* Scout Agent UI — Vue 3 Application */
console.log("[Scout] app.js loaded, Vue =", typeof Vue, "ElementPlus =", typeof ElementPlus);

const { createApp, ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } = Vue;

const app = createApp({
    setup() {
        // ── Icon map (Element Plus icons) ────────────────
        const iconMap = {
            CaretRight: ElementPlusIconsVue.CaretRight,
            UploadFilled: ElementPlusIconsVue.UploadFilled,
            Monitor: ElementPlusIconsVue.Monitor,
            ArrowRight: ElementPlusIconsVue.ArrowRight,
        };

        // ── State ────────────────────────────────────────
        const queryText = ref("");
        const uploadedFilePath = ref(null);
        const uploadRef = ref(null);
        const fileList = ref([]);
        const runId = ref(null);
        const isRunning = ref(false);
        const finalResult = ref(null);
        const runError = ref(null);
        const steps = ref([]);
        const workspaceEntries = ref([]);
        const trajectoryList = ref(null);
        let ws = null;
        let wsReconnectTimer = null;

        // ── Resizable panel widths ──────────────────────
        const queryWidth = ref(380);
        const dashWidth = ref(280);
        let resizeTarget = null;  // 'query' or 'dash'
        let resizeStartX = 0;
        let resizeStartWidth = 0;

        const config = reactive({
            server: "tencent",
            model: "venus,claude-4-5-sonnet-20250929",
            max_turns: 200,
            use_planner_agent: true,
            use_evaluator_agent: true,
        });

        const metrics = reactive({
            phase: "idle",
            turn: 0,
            max_turns: 200,
            input_tokens: 0,
            output_tokens: 0,
            tool_counts: {},
        });

        // ── Computed ─────────────────────────────────────

        const statusText = computed(() => {
            if (!runId.value) return "Ready";
            if (isRunning.value) return "Running";
            if (runError.value) return "Error";
            return "Completed";
        });

        const statusTagType = computed(() => {
            if (isRunning.value) return "warning";
            if (runError.value) return "danger";
            if (finalResult.value) return "success";
            return "info";
        });

        const phaseTagType = computed(() => {
            const m = { idle: "info", planning: "", gathering: "success", verifying: "warning" };
            return m[metrics.phase] || "info";
        });

        const turnPercentage = computed(() => {
            if (metrics.max_turns <= 0) return 0;
            return Math.min(100, Math.round((metrics.turn / metrics.max_turns) * 100));
        });

        const turnProgressColor = computed(() => {
            return "#09090b";
        });

        const sortedToolCounts = computed(() => {
            const entries = Object.entries(metrics.tool_counts);
            entries.sort((a, b) => b[1] - a[1]);
            return Object.fromEntries(entries);
        });

        // ── Tool call → result matching map ─────────────
        const toolCallStepMap = {};  // call_id → step index in steps[]

        // ── Methods ──────────────────────────────────────

        function formatNumber(n) {
            if (n === undefined || n === null) return "0";
            return n.toLocaleString();
        }

        function shortToolName(name) {
            return name.replace("mcp__long_utils__", "").replace("workspace_", "ws_");
        }

        function toolBarWidth(count) {
            const max = Math.max(...Object.values(metrics.tool_counts), 1);
            return Math.max(8, (count / max) * 100) + "%";
        }

        // ── Tool category / display helpers ──────────────

        function toolCategory(name) {
            if (!name) return "generic";
            const n = name.toLowerCase();
            if (n === "todowrite") return "todo";
            if (n === "read") return "read";
            if (n === "grep") return "grep";
            if (n === "glob") return "glob";
            if (n.includes("get_file_info")) return "file_info";
            if (n.includes("normalize_document")) return "normalize";
            if (n.includes("workspace_update")) return "ws_update";
            if (n.includes("workspace_view")) return "ws_view";
            if (n.includes("workspace_search")) return "ws_search";
            if (n.includes("workspace_evaluate")) return "ws_evaluate";
            return "generic";
        }

        function toolDisplayName(name) {
            const map = {
                todo: "Todo List",
                read: "Read File",
                grep: "Grep Search",
                glob: "Glob Files",
                file_info: "File Info",
                normalize: "Normalize",
                ws_update: "Workspace Update",
                ws_view: "Workspace View",
                ws_search: "Workspace Search",
                ws_evaluate: "Evaluate",
                generic: name || "Tool",
            };
            return map[toolCategory(name)] || name;
        }

        function toolIconChar(name) {
            const map = {
                todo: "\u2610",          // ballot box (checkbox)
                read: "\u2637",          // trigram (lines/page)
                grep: "\u2315",          // telephone recorder (search)
                glob: "\u25A1",          // white square (folder)
                file_info: "\u2139",     // info source
                normalize: "\u2261",     // identical to (normalize)
                ws_update: "\u2191",     // upwards arrow (update)
                ws_view: "\u25CE",       // bullseye (view)
                ws_search: "\u2316",     // position indicator (search)
                ws_evaluate: "\u2713",   // check mark
                generic: "\u2022",       // bullet
            };
            return map[toolCategory(name)] || "\u2022";
        }

        function toolBorderClass(name) {
            const cat = toolCategory(name);
            const map = {
                todo: "tool-border-dark",
                read: "tool-border-dark",
                grep: "tool-border-dark",
                glob: "tool-border-dark",
                file_info: "tool-border-dark",
                normalize: "tool-border-dark",
                ws_update: "tool-border-dark",
                ws_view: "tool-border-dark",
                ws_search: "tool-border-dark",
                ws_evaluate: "tool-border-dark",
                generic: "tool-border-dark",
            };
            return map[cat] || "tool-border-dark";
        }

        function extractResultText(content) {
            // Extract plain text from various result formats
            if (!content) return "";
            if (typeof content === "string") return content;
            // Array of {type: "text", text: "..."}
            if (Array.isArray(content)) {
                return content
                    .filter(c => c && c.type === "text")
                    .map(c => c.text || "")
                    .join("\n");
            }
            // Object with text field
            if (content.text) return content.text;
            // Object with content field
            if (content.content) return extractResultText(content.content);
            // Fallback
            return JSON.stringify(content, null, 2);
        }

        function parseResultJson(content) {
            // Try to parse result text as JSON, return parsed object or null
            const text = extractResultText(content);
            if (!text) return null;
            try {
                return JSON.parse(text);
            } catch {
                return null;
            }
        }

        function todoPriorityType(priority) {
            const map = { high: "danger", medium: "warning", low: "info" };
            return map[priority] || "info";
        }

        function todoStatusIcon(status) {
            const map = {
                completed: "\u2713",     // check mark
                in_progress: "\u2192",   // right arrow
                pending: "\u2013",       // en dash
                cancelled: "\u2717",     // ballot X
            };
            return map[status] || "\u2022";
        }

        function truncateText(text, maxLen) {
            if (!text || text.length <= maxLen) return text;
            return text.substring(0, maxLen) + "...";
        }

        // ── Step rendering helpers (updated for 'tool' type) ──

        function stepIcon(type) {
            const icons = {
                thinking: "\u2026",      // ellipsis (thinking)
                text: "\u2261",          // identical to (text lines)
                tool: "\u2022",          // bullet
                tool_call: "\u2192",     // right arrow (call)
                tool_result: "\u2190",   // left arrow (result)
            };
            return icons[type] || "\u2022";
        }

        function stepLabel(type) {
            const labels = {
                thinking: "Thinking",
                text: "Text",
                tool: "Tool",
                tool_call: "Tool Call",
                tool_result: "Tool Result",
            };
            return labels[type] || type;
        }

        function renderMarkdown(text) {
            if (!text) return "";
            try {
                return marked.parse(text);
            } catch (e) {
                return text.replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
            }
        }

        function formatJson(obj) {
            if (!obj) return "";
            if (typeof obj === "string") return obj;
            try {
                return JSON.stringify(obj, null, 2);
            } catch {
                return String(obj);
            }
        }

        function formatToolResult(content) {
            if (!content) return "";
            if (typeof content === "string") {
                // Try to parse if it looks like JSON
                try {
                    const parsed = JSON.parse(content);
                    return JSON.stringify(parsed, null, 2);
                } catch {
                    // Truncate very long strings
                    if (content.length > 2000) {
                        return content.substring(0, 2000) + "\n... (truncated)";
                    }
                    return content;
                }
            }
            return formatJson(content);
        }

        function toggleResultCollapse(step) {
            step.result_collapsed = !step.result_collapsed;
        }

        function expandAll() {
            steps.value.forEach(s => s.collapsed = false);
        }

        function collapseAll() {
            steps.value.forEach(s => s.collapsed = true);
        }

        function clearSteps() {
            steps.value = [];
            finalResult.value = null;
            runError.value = null;
            // Clear the tool call → step map
            Object.keys(toolCallStepMap).forEach(k => delete toolCallStepMap[k]);
        }

        function scrollToBottom() {
            nextTick(() => {
                const el = trajectoryList.value;
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            });
        }

        // ── Config ───────────────────────────────────────

        async function loadConfig() {
            try {
                const resp = await fetch("/api/config");
                const data = await resp.json();
                Object.assign(config, {
                    server: data.server || "tencent",
                    model: data.model || "venus,claude-4-5-sonnet-20250929",
                    max_turns: data.max_turns || 200,
                    use_planner_agent: data.use_planner_agent !== false,
                    use_evaluator_agent: data.use_evaluator_agent !== false,
                });
            } catch (e) {
                console.error("Failed to load config:", e);
            }
        }

        async function saveConfig() {
            try {
                await fetch("/api/config", {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(config),
                });
            } catch (e) {
                console.error("Failed to save config:", e);
            }
        }

        // ── File Upload ──────────────────────────────────

        function onUploadSuccess(response, file, currentFileList) {
            uploadedFilePath.value = response.file_path;
            fileList.value = [file];
            ElementPlus.ElMessage.success("File uploaded: " + response.file_name);
        }

        function onUploadError(err) {
            ElementPlus.ElMessage.error("Upload failed");
            console.error("Upload error:", err);
        }

        function onFileRemove() {
            uploadedFilePath.value = null;
            fileList.value = [];
        }

        function onUploadExceed(files) {
            // Auto-replace: clear old file, upload new one
            if (uploadRef.value) {
                uploadRef.value.clearFiles();
            }
            fileList.value = [];
            uploadedFilePath.value = null;
            // Manually trigger upload for the new file
            const file = files[0];
            if (file) {
                uploadRef.value.handleStart(file);
                uploadRef.value.submit();
            }
        }

        function resetAll() {
            // Reset all state for a fresh run
            queryText.value = "";
            uploadedFilePath.value = null;
            fileList.value = [];
            if (uploadRef.value) {
                uploadRef.value.clearFiles();
            }
            runId.value = null;
            isRunning.value = false;
            finalResult.value = null;
            runError.value = null;
            steps.value = [];
            workspaceEntries.value = [];
            metrics.phase = "idle";
            metrics.turn = 0;
            metrics.input_tokens = 0;
            metrics.output_tokens = 0;
            metrics.tool_counts = {};
            // Clear reconnection timer BEFORE closing ws to prevent stale reconnects
            if (wsReconnectTimer) {
                clearTimeout(wsReconnectTimer);
                wsReconnectTimer = null;
            }
            if (ws) {
                // Detach handlers to prevent onclose from scheduling reconnection
                ws.onclose = null;
                ws.onerror = null;
                ws.onmessage = null;
                ws.onopen = null;
                ws.close();
                ws = null;
            }
            stopPing();
            // Clear tool call map
            Object.keys(toolCallStepMap).forEach(k => delete toolCallStepMap[k]);
            ElementPlus.ElMessage.info("Reset complete");
        }

        // ── Query Execution ──────────────────────────────

        async function startQuery() {
            if (!queryText.value.trim() || isRunning.value) return;

            // Reset state
            clearSteps();
            isRunning.value = true;
            runError.value = null;
            finalResult.value = null;
            metrics.phase = "idle";
            metrics.turn = 0;
            metrics.input_tokens = 0;
            metrics.output_tokens = 0;
            metrics.tool_counts = {};

            try {
                // Start the query
                const resp = await fetch("/api/query", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        query: queryText.value,
                        file_path: uploadedFilePath.value,
                    }),
                });

                const data = await resp.json();
                runId.value = data.run_id;
                metrics.max_turns = config.max_turns;

                // Connect WebSocket for real-time events
                connectWebSocket(data.run_id);

            } catch (e) {
                isRunning.value = false;
                runError.value = "Failed to start query: " + e.message;
                ElementPlus.ElMessage.error("Failed to start query");
            }
        }

        // ── WebSocket ────────────────────────────────────

        function connectWebSocket(rid) {
            // CRITICAL: Clear any pending reconnection timer FIRST to prevent
            // reconnection storms (two timers fighting each other)
            if (wsReconnectTimer) {
                clearTimeout(wsReconnectTimer);
                wsReconnectTimer = null;
            }

            if (ws) {
                // Detach event handlers before closing to prevent onclose
                // from scheduling a stale reconnection timer
                ws.onclose = null;
                ws.onerror = null;
                ws.onmessage = null;
                ws.onopen = null;
                ws.close();
                ws = null;
            }

            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            const url = protocol + "//" + window.location.host + "/ws/events/" + rid;
            ws = new WebSocket(url);

            ws.onopen = () => {
                console.log("WebSocket connected for run:", rid);
                // Start keepalive ping
                startPing();
                // Poll status in case we missed events while disconnected
                pollRunStatus(rid);
            };

            ws.onmessage = (event) => {
                try {
                    const evt = JSON.parse(event.data);
                    handleEvent(evt);
                } catch (e) {
                    console.error("Failed to parse event:", e, event.data);
                }
            };

            ws.onerror = (err) => {
                console.error("WebSocket error:", err);
            };

            ws.onclose = () => {
                console.log("WebSocket closed for run:", rid);
                stopPing();
                // Only reconnect if STILL running AND this is still the current run
                // The stale runId check prevents the two-timer fight:
                // - User starts run A, ws connects to A
                // - User starts run B, connectWebSocket("B") nullifies A's handlers
                //   then closes A's ws, opens B's ws
                // - If B's ws closes and runId has changed to C, don't reconnect for B
                if (isRunning.value && runId.value === rid) {
                    console.log("Scheduling WebSocket reconnect for run:", rid);
                    wsReconnectTimer = setTimeout(() => connectWebSocket(rid), 2000);
                }
            };
        }

        let pingInterval = null;

        function startPing() {
            stopPing();
            pingInterval = setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send("ping");
                }
            }, 30000);
        }

        function stopPing() {
            if (pingInterval) {
                clearInterval(pingInterval);
                pingInterval = null;
            }
        }

        // ── Status Polling (recovery for missed events) ──

        async function pollRunStatus(rid) {
            // Called on WebSocket (re)connect to check if the run already
            // completed while we were disconnected. If so, fetch the result
            // and update the UI — recovering from missed run_completed events.
            if (!rid || !isRunning.value || runId.value !== rid) return;

            try {
                const resp = await fetch("/api/runs/" + rid + "/status");
                if (!resp.ok) return;
                const status = await resp.json();

                // If run is already completed or errored on the backend,
                // but the UI still thinks it's running, recover
                if (status.status === "completed" && isRunning.value && runId.value === rid) {
                    console.log("Recovered completed run via status poll:", rid);
                    // Fetch the full result
                    const resultResp = await fetch("/api/runs/" + rid + "/result");
                    if (resultResp.ok) {
                        const resultData = await resultResp.json();
                        // Synthesize a run_completed event
                        handleEvent({
                            type: "run_completed",
                            data: {
                                result: resultData.result || "",
                                tool_usage: resultData.tool_usage || {},
                                num_turns: resultData.num_turns || 0,
                            },
                        });
                    }
                } else if (status.status === "error" && isRunning.value && runId.value === rid) {
                    console.log("Recovered errored run via status poll:", rid);
                    handleEvent({
                        type: "run_error",
                        data: {
                            error: status.error || "Unknown error",
                        },
                    });
                }
                // If still running, update metrics from the status response
                if (status.status === "running" && runId.value === rid) {
                    if (status.input_tokens !== undefined) {
                        metrics.input_tokens = status.input_tokens;
                    }
                    if (status.output_tokens !== undefined) {
                        metrics.output_tokens = status.output_tokens;
                    }
                    if (status.tool_counts) {
                        metrics.tool_counts = status.tool_counts;
                    }
                    if (status.current_turn !== undefined) {
                        metrics.turn = status.current_turn;
                    }
                    if (status.phase) {
                        metrics.phase = status.phase;
                    }
                }
            } catch (e) {
                console.warn("Status poll failed:", e);
            }
        }

        function handleEvent(evt) {
            const { type, data } = evt;

            switch (type) {
                case "run_started":
                    metrics.phase = "planning";
                    break;

                case "thinking":
                    steps.value.push({
                        type: "thinking",
                        step: data.step || steps.value.length + 1,
                        content: data.content,
                        collapsed: true,  // thinking collapsed by default
                    });
                    scrollToBottom();
                    break;

                case "text":
                    steps.value.push({
                        type: "text",
                        step: data.step || steps.value.length + 1,
                        content: data.content,
                        collapsed: true,
                    });
                    scrollToBottom();
                    break;

                case "tool_call":
                    steps.value.push({
                        type: "tool",
                        step: data.step || steps.value.length + 1,
                        tool_name: data.tool_name,
                        tool_input: data.tool_input,
                        call_id: data.call_id,
                        category: toolCategory(data.tool_name),
                        collapsed: true,
                        loading: true,         // waiting for result
                        result: null,
                        result_error: false,
                        result_collapsed: true, // result section collapsed by default
                    });
                    toolCallStepMap[data.call_id] = steps.value.length - 1;
                    scrollToBottom();
                    break;

                case "tool_result": {
                    const idx = toolCallStepMap[data.call_id];
                    if (idx !== undefined && steps.value[idx]) {
                        // Merge result into the existing tool step
                        const s = steps.value[idx];
                        s.loading = false;
                        s.result = data.content;
                        s.result_error = !!data.is_error;
                        s.result_collapsed = true;  // keep collapsed, user can expand manually
                    } else {
                        // Fallback: no matching call found — create standalone
                        steps.value.push({
                            type: "tool_result",
                            step: data.step || steps.value.length + 1,
                            content: data.content,
                            is_error: data.is_error,
                            call_id: data.call_id,
                            collapsed: true,
                        });
                    }
                    scrollToBottom();
                    break;
                }

                case "phase_change":
                    metrics.phase = data.phase || "idle";
                    break;

                case "metrics_update":
                    metrics.input_tokens = data.input_tokens || 0;
                    metrics.output_tokens = data.output_tokens || 0;
                    metrics.tool_counts = data.tool_counts || {};
                    metrics.turn = data.turn || 0;
                    if (data.max_turns) metrics.max_turns = data.max_turns;
                    if (data.phase) metrics.phase = data.phase;
                    break;

                case "workspace_update":
                    if (data.entries) {
                        workspaceEntries.value = data.entries.map(e => ({
                            ...e,
                            _expanded: false,
                        }));
                    }
                    break;

                case "run_completed":
                    isRunning.value = false;
                    finalResult.value = data.result || "";
                    metrics.phase = "idle";
                    if (data.tool_usage) metrics.tool_counts = data.tool_usage;
                    if (data.num_turns) metrics.turn = data.num_turns;
                    scrollToBottom();
                    // Fetch workspace entries
                    fetchWorkspace(runId.value);
                    ElementPlus.ElMessage.success("Query completed");
                    break;

                case "run_error":
                    isRunning.value = false;
                    runError.value = data.error || "Unknown error";
                    metrics.phase = "idle";
                    scrollToBottom();
                    ElementPlus.ElMessage.error("Query failed: " + (data.error || "Unknown error"));
                    break;

                case "pong":
                    break;

                default:
                    console.log("Unknown event type:", type, data);
            }
        }

        // ── Workspace Fetch ──────────────────────────────

        async function fetchWorkspace(rid) {
            if (!rid) return;
            try {
                const resp = await fetch("/api/runs/" + rid + "/workspace");
                const data = await resp.json();
                if (data.entries) {
                    workspaceEntries.value = data.entries.map(e => ({
                        ...e,
                        _expanded: false,
                    }));
                }
            } catch (e) {
                console.error("Failed to fetch workspace:", e);
            }
        }

        // ── Panel Resize ─────────────────────────────────

        function startResize(event, target) {
            event.preventDefault();
            resizeTarget = target;
            resizeStartX = event.clientX;
            resizeStartWidth = target === "query" ? queryWidth.value : dashWidth.value;
            document.body.classList.add("col-resizing");
            document.addEventListener("mousemove", onResize);
            document.addEventListener("mouseup", stopResize);
        }

        function onResize(event) {
            const dx = event.clientX - resizeStartX;
            if (resizeTarget === "query") {
                // Dragging right divider of query panel: increase width with rightward drag
                queryWidth.value = Math.max(240, Math.min(600, resizeStartWidth + dx));
            } else if (resizeTarget === "dash") {
                // Dragging left divider of dashboard panel: decrease width with rightward drag
                dashWidth.value = Math.max(200, Math.min(500, resizeStartWidth - dx));
            }
        }

        function stopResize() {
            resizeTarget = null;
            document.body.classList.remove("col-resizing");
            document.removeEventListener("mousemove", onResize);
            document.removeEventListener("mouseup", stopResize);
        }

        // ── Lifecycle ────────────────────────────────────

        onMounted(() => {
            loadConfig();
        });

        onUnmounted(() => {
            if (wsReconnectTimer) {
                clearTimeout(wsReconnectTimer);
                wsReconnectTimer = null;
            }
            if (ws) {
                ws.onclose = null;
                ws.onerror = null;
                ws.onmessage = null;
                ws.onopen = null;
                ws.close();
                ws = null;
            }
            stopPing();
        });

        // ── Return ───────────────────────────────────────

        return {
            iconMap,
            queryText,
            uploadedFilePath,
            uploadRef,
            fileList,
            runId,
            isRunning,
            finalResult,
            runError,
            steps,
            workspaceEntries,
            config,
            metrics,
            trajectoryList,
            queryWidth,
            dashWidth,
            statusText,
            statusTagType,
            phaseTagType,
            turnPercentage,
            turnProgressColor,
            sortedToolCounts,
            formatNumber,
            shortToolName,
            toolBarWidth,
            toolCategory,
            toolDisplayName,
            toolIconChar,
            toolBorderClass,
            extractResultText,
            parseResultJson,
            todoPriorityType,
            todoStatusIcon,
            truncateText,
            stepIcon,
            stepLabel,
            renderMarkdown,
            formatJson,
            formatToolResult,
            toggleResultCollapse,
            expandAll,
            collapseAll,
            clearSteps,
            saveConfig,
            onUploadSuccess,
            onUploadError,
            onFileRemove,
            onUploadExceed,
            resetAll,
            startQuery,
            startResize,
        };
    },
});

// Register Element Plus
app.use(ElementPlus);

// Register all Element Plus icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

app.mount("#app");
console.log("[Scout] Vue app mounted");

// Hide loading placeholder once Vue has mounted
const loadingEl = document.getElementById("loading-placeholder");
if (loadingEl) loadingEl.style.display = "none";
