import { getAssetIcon } from './assetIcons';

export function AssetBadge({ symbol, category, size = 'regular' }: { symbol: string; category?: string; size?: 'compact' | 'regular' | 'large' }) {
  const displaySymbol = symbol.trim().toUpperCase().replace(/-USD$/, '');
  const icon = getAssetIcon(displaySymbol, category);
  return (
    <span className={`asset-badge asset-badge--${icon.kind} asset-badge--${size}`} aria-hidden="true">
      {icon.kind === 'crypto' && displaySymbol === 'ETH' ? (
        <svg viewBox="0 0 24 24"><path d="M12 2 6.5 12 12 15.2 17.5 12 12 2Z"/><path d="m6.5 13.1 5.5 8.1 5.5-8.1-5.5 3.2-5.5-3.2Z"/></svg>
      ) : icon.kind === 'etf' ? (
        <svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>
      ) : <span>{icon.mark}</span>}
    </span>
  );
}
