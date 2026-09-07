import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OpportunityCost } from './OpportunityCost';
import type { Asset } from './types';

const assets: Asset[] = ['BTC', 'AAPL', 'NVDA', 'SPY', 'QQQ', 'GLD'].map((symbol) => ({
  symbol, name: symbol, category: symbol === 'BTC' ? 'crypto' : 'stock',
}));

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ products: [], categories: [] }),
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function addCustom(name = 'Sony OLED TV') {
  fireEvent.click(screen.getByRole('button', { name: /^Add custom purchase$/i }));
  fireEvent.change(screen.getByLabelText('Custom purchase name'), { target: { value: name } });
  fireEvent.change(screen.getByLabelText('Custom purchase date'), { target: { value: '2018-11-23' } });
  fireEvent.change(screen.getByLabelText('Custom purchase price'), { target: { value: '1999.99' } });
  fireEvent.click(screen.getByRole('button', { name: /^Add purchase$/i }));
}

describe('Opportunity Cost custom purchases', () => {
  it('creates, edits, persists, changes quantity, and removes a custom purchase', async () => {
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    expect(screen.getByText('Sony OLED TV')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Add one Sony OLED TV'));
    await waitFor(() => expect(localStorage.getItem('hunter3.opportunity-custom-purchases.v1')).toContain('"quantity":2'));

    fireEvent.click(screen.getByLabelText('Edit Sony OLED TV'));
    fireEvent.change(screen.getByLabelText('Custom purchase name'), { target: { value: 'Living room TV' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(screen.getByText('Living room TV')).toBeInTheDocument();
    expect(localStorage.getItem('hunter3.opportunity-custom-purchases.v1')).toContain('Living room TV');

    fireEvent.click(screen.getByLabelText('Delete Living room TV'));
    expect(screen.queryByText('Living room TV')).not.toBeInTheDocument();
  });

  it('shows validation feedback for invalid custom purchases', () => {
    render(<OpportunityCost assets={assets}/>);
    fireEvent.click(screen.getByRole('button', { name: /^Add custom purchase$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Add purchase$/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a name');
  });
});

describe('Opportunity Cost asset comparison', () => {
  it('persists up to five assets and explains the limit', async () => {
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    fireEvent.click(screen.getByRole('button', { name: /Add asset/i }));
    for (const symbol of ['AAPL', 'NVDA', 'SPY', 'QQQ']) {
      fireEvent.click(screen.getByRole('button', { name: `${symbol} ${symbol}` }));
    }
    fireEvent.click(screen.getByRole('button', { name: 'GLD GLD' }));
    expect(screen.getByRole('alert')).toHaveTextContent('up to 5 assets');
    await waitFor(() => expect(JSON.parse(localStorage.getItem('hunter3.opportunity-assets.v1') ?? '[]')).toHaveLength(5));
  });
});
