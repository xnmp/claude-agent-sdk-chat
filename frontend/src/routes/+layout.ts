// Static SPA build: all pages rendered client-side. adapter-static
// with fallback: 'index.html' requires SSR off so routes don't try to
// prerender against the FastAPI API during `vite build`.
export const ssr = false;
export const prerender = false;
