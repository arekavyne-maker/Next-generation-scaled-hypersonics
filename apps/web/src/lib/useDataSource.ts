import { useEffect, useState } from 'react';
import { getDataSourceState, subscribeDataSource, type DataSourceState } from '../api/client';

/**
 * Tracks whether the console is reading live services or the mock fallback.
 * The sidebar badge, the top bar and the status tiles all read from this.
 */
export function useDataSource(): DataSourceState {
  const [state, setState] = useState<DataSourceState>(getDataSourceState);
  useEffect(() => subscribeDataSource(setState), []);
  return state;
}
