export type AssetIcon = { mark: string; kind: 'crypto' | 'stock' | 'etf' | 'metal' };

const ASSET_ICONS: Readonly<Record<string, AssetIcon>> = {
  BTC: { mark: '₿', kind: 'crypto' }, ETH: { mark: '◆', kind: 'crypto' },
  AAPL: { mark: 'A', kind: 'stock' }, MSFT: { mark: 'M', kind: 'stock' },
  GOOGL: { mark: 'G', kind: 'stock' }, AMZN: { mark: 'A', kind: 'stock' }, NVDA: { mark: 'N', kind: 'stock' },
  META: { mark: 'M', kind: 'stock' }, TSLA: { mark: 'T', kind: 'stock' },
  SPY: { mark: 'S', kind: 'etf' }, QQQ: { mark: 'Q', kind: 'etf' },
  GLD: { mark: 'Au', kind: 'metal' }, SLV: { mark: 'Ag', kind: 'metal' },
  PPLT: { mark: 'Pt', kind: 'metal' },
};

/** Return a restrained, text-native asset mark with no external logo dependency. */
export function getAssetIcon(symbol: string, category?: string): AssetIcon {
  const normalized = symbol.trim().toUpperCase();
  const kind = category === 'crypto' ? 'crypto' : category === 'etf' ? 'etf' : category === 'precious_metal_etf' ? 'metal' : 'stock';
  return ASSET_ICONS[normalized] ?? { mark: normalized.charAt(0) || '?', kind };
}
