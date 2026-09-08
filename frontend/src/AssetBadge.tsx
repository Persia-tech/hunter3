import { getAssetIcon } from './assetIcons';

type AssetBadgeProps = {
  symbol: string;
  category?: string;
  size?: 'compact' | 'regular';
};

function toneFor(symbol: string, category?: string) {
  const normalized = symbol.toUpperCase();
  if (normalized === 'BTC') return 'bitcoin';
  if (['GLD', 'SLV', 'PPLT'].includes(normalized) || category?.includes('metal')) return 'metal';
  if (['SPY', 'QQQ'].includes(normalized) || category?.includes('etf')) return 'etf';
  return 'stock';
}

/** A local, text-native asset identity with no image or network dependency. */
export function AssetBadge({ symbol, category, size = 'regular' }: AssetBadgeProps) {
  const icon = getAssetIcon(symbol);
  return (
    <span
      className={`asset-badge asset-badge-${toneFor(symbol, category)} asset-badge-${size} ${icon.kind ?? ''}`.trim()}
      aria-hidden="true"
    >
      {icon.mark}
    </span>
  );
}
