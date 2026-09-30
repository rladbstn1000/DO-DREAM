import type { Sample } from './samples';
import type { ShowcaseStore } from './store';
import type { OriginalStore } from './originalStore';
export type ShowcasePort = {
  samples: readonly Sample[];
  findSample: (id: string | undefined) => Sample | undefined;
  store: ShowcaseStore;
  uiStore: OriginalStore;
  getEpoch: () => number;
};
