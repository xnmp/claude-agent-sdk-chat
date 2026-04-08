import type { WsMessage } from './types';

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

const BASE_DELAY = 1000;
const MAX_DELAY = 30000;
const MAX_RETRIES = 10;

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
		disconnect,
		setOnStatusChange,
		setOnDisconnect,
		getStatus: () => status
	};
}

export type WsClient = ReturnType<typeof createWsClient>;
