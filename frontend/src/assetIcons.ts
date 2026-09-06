export type AssetIcon = { mark: string; kind?: 'grid' | 'metal' };

const ASSET_ICONS: Readonly<Record<string, AssetIcon>> = {
  BTC: { mark: '₿' }, AAPL: { mark: 'A' }, MSFT: { mark: '⊞', kind: 'grid' },
  GOOGL: { mark: 'G' }, AMZN: { mark: 'A' }, NVDA: { mark: 'N' },
  META: { mark: 'M' }, TSLA: { mark: 'T' }, SPY: { mark: 'S' }, QQQ: { mark: 'Q' },
  GLD: { mark: 'Au', kind: 'metal' }, SLV: { mark: 'Ag', kind: 'metal' },
  PPLT: { mark: 'Pt', kind: 'metal' },
};

/** Return a restrained, text-native asset mark with no external logo dependency. */
export function getAssetIcon(symbol: string): AssetIcon {
  const normalized = symbol.trim().toUpperCase();
  return ASSET_ICONS[normalized] ?? { mark: normalized.charAt(0) || '?' };
}
