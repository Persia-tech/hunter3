import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OpportunityCost } from './OpportunityCost';
import type { Asset } from './types';

const assets: Asset[] = ['BTC', 'AAPL', 'NVDA', 'SPY', 'QQQ', 'GLD'].map((symbol) => ({
  symbol, name: symbol === 'GLD' ? 'Gold' : symbol, category: symbol === 'BTC' ? 'crypto' : 'stock',
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
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: name } });
  fireEvent.change(screen.getByLabelText('Purchase date'), { target: { value: '2018-11-23' } });
  fireEvent.change(screen.getByLabelText('Price USD'), { target: { value: '1999.99' } });
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
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Living room TV' } });
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
    expect(screen.getByRole('dialog', { name: 'Add something you bought' })).toHaveAttribute('aria-modal', 'true');
  });
});

describe('Opportunity Cost asset comparison', () => {
  it('persists up to five assets and explains the limit', async () => {
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    fireEvent.click(screen.getByRole('button', { name: /Add asset/i }));
    for (const symbol of ['AAPL', 'NVDA', 'SPY', 'QQQ']) {
      fireEvent.click(screen.getByRole('button', { name: new RegExp(symbol) }));
    }
    fireEvent.click(screen.getByRole('button', { name: /GLD/ }));
    expect(screen.getByText(/Maximum reached/)).toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(localStorage.getItem('hunter3.opportunity-assets.v1') ?? '[]')).toHaveLength(5));
  });

  it('searches the accessible asset sheet and restores selected assets', async () => {
    localStorage.setItem('hunter3.opportunity-assets.v1', JSON.stringify(['BTC', 'NVDA']));
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    expect(screen.getByRole('button', { name: 'Remove NVDA' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Add asset/i }));
    const search = screen.getByLabelText('Search assets');
    fireEvent.change(search, { target: { value: 'Gold' } });
    expect(screen.queryByRole('button', { name: /AAPL/ })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Choose assets' })).toHaveAttribute('aria-modal', 'true');
  });
});

it('progressively discloses purchases, timeline entries, and rankings', async () => {
  const custom = Array.from({ length: 6 }, (_, index) => ({ id: `custom:item-${index}`, name: `Item ${index}`, purchase_date: '2018-11-23', price_usd: '100', quantity: 1, category: 'Other', custom: true }));
  localStorage.setItem('hunter3.opportunity-custom-purchases.v1', JSON.stringify(custom));
  const items = custom.map((item) => ({ product: { id: item.id, brand: 'Custom', category: 'Other', family: 'Custom', model: item.name, release_date: item.purchase_date, release_year: 2018, launch_price_usd: item.price_usd, image_url: null, source_url: '', active: true, display_order: 0, custom: true }, quantity: 1, cost: '100', eligible: true, requested_date: item.purchase_date, price_date: item.purchase_date, asset_price: '10', units: '10', current_value: '1000', gain: '900', reason: null }));
  const result = { asset: assets[0], current_price: '100', current_price_date: '2026-01-01', summary: { total_spent: '600', eligible_spent: '600', current_value: '6000', gain: '5400', return_pct: '900', investment_units: '60', eligible_items: 6, total_items: 6 }, items };
  const rankings = Array.from({ length: 7 }, (_, index) => ({ ...result, asset: { ...assets[index % assets.length], symbol: `R${index}` }, summary: { ...result.summary, current_value: String(7000 - index) } }));
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes('best-alternatives') ? { rankings, snapshot_id: 'b'.repeat(32) } : url.includes('/compare') ? { results: [result], unavailable: [], snapshot_id: 'a'.repeat(32) } : { products: [], categories: [] } })));
  render(<OpportunityCost assets={assets}/>);
  expect(screen.getByRole('button', { name: 'Show all 6 purchases' })).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(screen.getByRole('button', { name: 'Show all 6 purchases' }));
  fireEvent.click(screen.getByRole('button', { name: 'Compare investments' }));
  expect(await screen.findByRole('button', { name: 'Show all 6 purchases' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Show fewer purchases' })).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('button', { name: 'Show all 6 purchases' })).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(screen.getByRole('button', { name: 'Scan all assets' }));
  expect(await screen.findByRole('button', { name: 'Show all 7 assets' })).toBeInTheDocument();
  expect(screen.queryByText('R6')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Show all 7 assets' }));
  expect(screen.getByText('R6')).toBeInTheDocument();
});
