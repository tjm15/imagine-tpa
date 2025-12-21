import { useEffect, useState } from 'react';

export interface VisualAsset {
  visual_asset_id: string;
  document_id: string | null;
  page_number: number | null;
  asset_type: string | null;
  blob_path: string | null;
  metadata: Record<string, any>;
  authority_id: string | null;
  plan_cycle_id: string | null;
}

const API_PREFIX = '/api';

export function useVisualAssets(authorityId?: string | null) {
  const [assets, setAssets] = useState<VisualAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authorityId) {
      setAssets([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetch(`${API_PREFIX}/visual-assets?authority_id=${authorityId}`, {
          signal: controller.signal,
        });
        if (!resp.ok) {
          throw new Error(`Visual assets fetch failed: ${resp.status}`);
        }
        const data = (await resp.json()) as { visual_assets?: VisualAsset[] };
        setAssets(Array.isArray(data.visual_assets) ? data.visual_assets : []);
      } catch (err) {
        console.error(err);
        setError(err instanceof Error ? err.message : 'Failed to load visual assets');
        setAssets([]);
      } finally {
        setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [authorityId]);

  return { assets, loading, error };
}

export async function fetchVisualAssetBlob(visualAssetId: string): Promise<string> {
  const resp = await fetch(`${API_PREFIX}/visual-assets/${visualAssetId}/blob`);
  if (!resp.ok) {
    throw new Error(`Visual blob fetch failed: ${resp.status}`);
  }
  const data = (await resp.json()) as { data_url?: string };
  if (!data.data_url) {
    throw new Error('Visual blob missing data_url');
  }
  return data.data_url;
}
