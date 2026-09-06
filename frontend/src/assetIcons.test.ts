import { describe, expect, it } from 'vitest';
import { getAssetIcon } from './assetIcons';

describe('asset icon mapping', () => {
  it('uses the Bitcoin currency symbol', () => expect(getAssetIcon('BTC').mark).toBe('₿'));

  it.each([
    ['AAPL', 'A'], ['MSFT', '⊞'], ['GOOGL', 'G'], ['SPY', 'S'], ['QQQ', 'Q'],
    ['GLD', 'Au'], ['SLV', 'Ag'], ['PPLT', 'Pt'],
  ])('maps %s to %s', (symbol, mark) => expect(getAssetIcon(symbol).mark).toBe(mark));

  it('falls back to a normalized first letter', () => {
    expect(getAssetIcon(' xyz ')).toEqual({ mark: 'X' });
    expect(getAssetIcon('')).toEqual({ mark: '?' });
  });
});
