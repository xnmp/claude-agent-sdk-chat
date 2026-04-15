import type { WsMessage } from './types';

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

const BASE_DELAY = 1000;
const MAX_DELAY = 30000;
const MAX_RETRIES = 10;

// -- Logging helpers -------------------------------------------------------
//
// Mirror of the backend's _block_summary / _short_args / _short_id helpers
// in backend/infra/sdk_manager.py, so a single log format for a tool call
// looks the same end-to-end:
//   backend: tool_use(Read,id=01Abc123,{"file_path":"/tmp/…"})
//   frontend: [ws] tool_use(Read,id=01Abc123)  then  tool_input(id=01Abc123,{…})

const preview = (s: string, n = 15): string => {
	const head = s.slice(0, n).replace(/\n/g, ' ');
	return `"${head}${s.length > n ? '…' : ''}"`;
};

const shortId = (s: string): string => (s.length > 8 ? s.slice(-8) : s);

const shortArgs = (args: Record<string, unknown>): string => {
	const parts = Object.entries(args).map(([k, v]) => {
		const s = typeof v === 'string' ? v : JSON.stringify(v);
		const head = s.slice(0, 15).replace(/\n/g, ' ');
		const body = `${head}${s.length > 15 ? '…' : ''}`;
		return typeof v === 'string' ? `"${k}":"${body}"` : `"${k}":${body}`;
	});
	return `{${parts.join(',')}}`;
};

const shortResult = (s: string): string => preview(s, 30);

function summarizeWsMessage(msg: WsMessage): string {
	switch (msg.type) {
		case 'thinking':
			return `thinking(${msg.thinking.length},${preview(msg.thinking)})`;
		case 'assistant_text':
			return `assistant_text(${msg.text.length},${preview(msg.text)})`;
		case 'text_block_start':
			return `text_block_start(#${msg.block_index})`;
		case 'text_delta':
			return `text_delta(#${msg.block_index},${preview(msg.text)})`;
		case 'thinking_block_start':
			return `thinking_block_start(#${msg.block_index})`;
		case 'thinking_delta':
			return `thinking_delta(#${msg.block_index},${preview(msg.thinking)})`;
		case 'tool_use':
			return `tool_use(${msg.name},id=${shortId(msg.id)})`;
		case 'tool_input':
			return `tool_input(id=${shortId(msg.tool_use_id)},${shortArgs(msg.input)})`;
		case 'tool_result':
			return `tool_result(id=${shortId(msg.tool_use_id)},${shortResult(msg.content)}${msg.is_error ? ',ERROR' : ''})`;
		case 'result':
			return `result(${msg.duration_ms}ms,$${(msg.total_cost_usd ?? 0).toFixed(4)},turns=${msg.num_turns},error=${msg.is_error})`;
		case 'error':
			return `error(${preview(msg.message, 40)})`;
		case 'suggestions':
			return `suggestions(${msg.questions.length})`;
		case 'title_update':
			return `title_update(${preview(msg.title)})`;
	}
}

export function createWsClient(conversationId: string, onMessage: (msg: WsMessage) => void) {
	let ws: WebSocket | null = null;
	let status: WsStatus = 'disconnected';
	let onStatusChange: ((s: WsStatus) => void) | null = null;
	let onDisconnect: (() => void) | null = null;
	let retryCount = 0;
	let retryTimer: ReturnType<typeof setTimeout> | null = null;
	let intentionalClose = false;

	function setStatus(s: WsStatus) {
		status = s;
		onStatusChange?.(s);
	}

	function connect() {
		intentionalClose = false;
		_open();
	}

	function _open() {
		if (ws) {
			ws.close();
		}
		setStatus(retryCount === 0 ? 'connecting' : 'reconnecting');
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		ws = new WebSocket(`${protocol}//localhost:8000/api/ws/${conversationId}`);

		ws.onopen = () => {
			retryCount = 0;
			setStatus('connected');
		};

		ws.onmessage = (event) => {
			try {
				const msg: WsMessage = JSON.parse(event.data);
				console.log(`[ws] ${summarizeWsMessage(msg)}`);
				onMessage(msg);
			} catch {
				// ignore malformed messages
			}
		};

		ws.onclose = () => {
			ws = null;
			if (intentionalClose) {
				setStatus('disconnected');
				return;
			}
			// Unexpected close — notify and attempt reconnection
			onDisconnect?.();
			_scheduleReconnect();
		};

		ws.onerror = () => {
			// onclose will fire after onerror, which handles reconnection
		};
	}

	function _scheduleReconnect() {
		if (retryCount >= MAX_RETRIES) {
			setStatus('disconnected');
			return;
		}
		setStatus('reconnecting');
		const delay = Math.min(BASE_DELAY * 2 ** retryCount, MAX_DELAY);
		retryCount++;
		retryTimer = setTimeout(_open, delay);
	}

	function send(content: string, attachmentIds: string[] = []) {
		ws?.send(JSON.stringify({ type: 'user_message', content, attachment_ids: attachmentIds }));
	}

	function interrupt() {
		ws?.send(JSON.stringify({ type: 'interrupt' }));
	}

	function answerQuestion(answer: string) {
		ws?.send(JSON.stringify({ type: 'question_answer', answer }));
	}

	function disconnect() {
		intentionalClose = true;
		if (retryTimer) {
			clearTimeout(retryTimer);
			retryTimer = null;
		}
		ws?.close();
		ws = null;
		setStatus('disconnected');
	}

	function setOnStatusChange(cb: (s: WsStatus) => void) {
		onStatusChange = cb;
	}

	function setOnDisconnect(cb: () => void) {
		onDisconnect = cb;
	}

	return {
		connect,
		send,
		interrupt,
		answerQuestion,
		disconnect,
		setOnStatusChange,
		setOnDisconnect,
		getStatus: () => status
	};
}

export type WsClient = ReturnType<typeof createWsClient>;
