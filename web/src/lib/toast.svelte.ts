export type Toast = { id: number; text: string; kind: 'info' | 'error' };

export const toasts = $state<Toast[]>([]);
let seq = 0;

export function toast(text: string, kind: 'info' | 'error' = 'info') {
  const id = ++seq;
  toasts.push({ id, text, kind });
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, kind === 'error' ? 6000 : 3000);
}

export function errorToast(e: unknown) {
  toast(e instanceof Error ? e.message : String(e), 'error');
}
