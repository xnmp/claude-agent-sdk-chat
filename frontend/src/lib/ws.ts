import type { WsMessage } from './types';

export type WsStatus = 'disconnected' | 'connecting' | 'connected';

export function createWsClient(conversationId: string, onMessage: (msg: WsMessage) => void) {
	let ws: WebSocket | null = null;
	let status: WsStatus = 'disconnected';
	let onStatusChange: ((s: WsStatus) => void) | null = null;

	function setStatus(s: WsStatus) {
		status = s;
		onStatusChange?.(s);
	}

	function connect() {
		if (ws) {
			ws.close();
		}
		setStatus('connecting');
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		ws = new WebSocket(`${protocol}//localhost:8000/api/ws/${conversationId}`);

		ws.onopen = () => setStatus('connected');

		ws.onmessage = (event) => {
			try {
				const msg: WsMessage = JSON.parse(event.data);
				onMessage(msg);
			} catch {
				// ignore malformed messages
			}
		};

		ws.onclose = () => {
			setStatus('disconnected');
			ws = null;
		};

		ws.onerror = () => {
			ws?.close();
		};
	}

	function send(content: string) {
		ws?.send(JSON.stringify({ type: 'user_message', content }));
	}

	function interrupt() {
		ws?.send(JSON.stringify({ type: 'interrupt' }));
	}

	function disconnect() {
		ws?.close();
		ws = null;
		setStatus('disconnected');
	}

	function setOnStatusChange(cb: (s: WsStatus) => void) {
		onStatusChange = cb;
	}

	return { connect, send, interrupt, disconnect, setOnStatusChange, getStatus: () => status };
}

export type WsClient = ReturnType<typeof createWsClient>;
