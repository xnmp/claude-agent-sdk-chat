/**
 * User settings — persisted to localStorage.
 * Pure module with no Svelte dependency.
 */

export interface Settings {
	theme: 'light' | 'dark';
	showCost: boolean;
	showDuration: boolean;
}

const STORAGE_KEY = 'settings';

const DEFAULTS: Settings = {
	theme: 'light',
	showCost: true,
	showDuration: true
};

export function loadSettings(): Settings {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (raw) {
			return { ...DEFAULTS, ...JSON.parse(raw) };
		}
	} catch {
		// corrupt data — fall back to defaults
	}
	return { ...DEFAULTS };
}

export function saveSettings(settings: Settings): void {
	localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function applyTheme(theme: 'light' | 'dark'): void {
	document.documentElement.setAttribute('data-theme', theme);
}
