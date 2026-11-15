import type { User } from './types';

export const session = $state<{ user: User | null }>({ user: null });
