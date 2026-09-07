import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
  it('creates, edits, changes quantity, and removes a custom purchase during the session', () => {
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    expect(screen.getByText('Sony OLED TV')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Add one Sony OLED TV'));
    expect(screen.getByText('2')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Edit Sony OLED TV'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Living room TV' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(screen.getByText('Living room TV')).toBeInTheDocument();

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
  it('selects up to five assets during the session and explains the limit', () => {
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    fireEvent.click(screen.getByRole('button', { name: /Add asset/i }));
    for (const symbol of ['AAPL', 'NVDA', 'SPY', 'QQQ']) {
      fireEvent.click(screen.getByRole('button', { name: new RegExp(symbol) }));
    }
    fireEvent.click(screen.getByRole('button', { name: /GLD/ }));
    expect(screen.getByText(/Maximum reached/)).toBeInTheDocument();
    for (const symbol of ['BTC', 'AAPL', 'NVDA', 'SPY', 'QQQ']) {
      expect(screen.getByRole('button', { name: `Remove ${symbol}` })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'Remove GLD' })).not.toBeInTheDocument();
  });

  it('searches the accessible asset sheet', () => {
    render(<OpportunityCost assets={assets}/>);
    addCustom();
    fireEvent.click(screen.getByRole('button', { name: /Add asset/i }));
    const search = screen.getByLabelText('Search assets');
    fireEvent.change(search, { target: { value: 'Gold' } });
    expect(screen.queryByRole('button', { name: /AAPL/ })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Choose assets' })).toHaveAttribute('aria-modal', 'true');
  });
});

it('ignores old scenario storage and starts with an empty BTC scenario', () => {
  localStorage.setItem('hunter3.opportunity-purchases.v1', JSON.stringify({ 'iphone-x': 1 }));
  localStorage.setItem('hunter3.opportunity-custom-purchases.v1', JSON.stringify([{ id: 'custom:old', name: 'Old TV' }]));
  localStorage.setItem('hunter3.opportunity-assets.v1', JSON.stringify(['NVDA', 'SPY']));
  render(<OpportunityCost assets={assets}/>);
  expect(screen.getByText('Start with something you bought')).toBeInTheDocument();
  expect(screen.queryByText('Old TV')).not.toBeInTheDocument();
  addCustom('Fresh purchase');
  expect(screen.getByRole('button', { name: 'Remove BTC' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Remove NVDA' })).not.toBeInTheDocument();
});

it('progressively discloses content and Start over resets the complete scenario', async () => {
  const catalog = Array.from({ length: 6 }, (_, index) => ({ id: `item-${index}`, brand: 'Test', category: 'Test', family: 'Test', model: `Item ${index}`, release_date: '2018-11-23', release_year: 2018, launch_price_usd: '100', image_url: null, source_url: '', active: true, display_order: index, custom: false }));
  const items = catalog.map((product) => ({ product, quantity: 1, cost: '100', eligible: true, requested_date: product.release_date, price_date: product.release_date, asset_price: '10', units: '10', current_value: '1000', gain: '900', reason: null }));
  const result = { asset: assets[0], current_price: '100', current_price_date: '2026-01-01', summary: { total_spent: '600', eligible_spent: '600', current_value: '6000', gain: '5400', return_pct: '900', investment_units: '60', eligible_items: 6, total_items: 6 }, items };
  const rankings = Array.from({ length: 7 }, (_, index) => ({ ...result, asset: { ...assets[index % assets.length], symbol: `R${index}` }, summary: { ...result.summary, current_value: String(7000 - index) } }));
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes('best-alternatives') ? { rankings, snapshot_id: 'b'.repeat(32) } : url.includes('/compare') ? { results: [result], unavailable: [], snapshot_id: 'a'.repeat(32) } : { products: catalog, categories: ['Test'] } })));
  render(<OpportunityCost assets={assets}/>);
  for (const product of catalog) fireEvent.click(await screen.findByRole('button', { name: new RegExp(product.model) }));
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
  fireEvent.click(screen.getByRole('button', { name: 'Start over' }));
  expect(screen.getByText('Start with something you bought')).toBeInTheDocument();
  addCustom('After reset');
  expect(screen.getByRole('button', { name: 'Remove BTC' })).toBeInTheDocument();
  expect(screen.queryByText('Best selected alternative')).not.toBeInTheDocument();
  expect(screen.queryByText('R0')).not.toBeInTheDocument();
});

it('Start over clears custom purchases and restores BTC as the only asset', () => {
  render(<OpportunityCost assets={assets}/>);
  addCustom('Current session purchase');
  fireEvent.click(screen.getByRole('button', { name: /Add asset/i }));
  fireEvent.click(screen.getByRole('button', { name: /NVDA/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Done' }));
  expect(screen.getByRole('button', { name: 'Remove NVDA' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start over' }));
  expect(screen.queryByText('Current session purchase')).not.toBeInTheDocument();
  addCustom('After reset');
  expect(screen.getByRole('button', { name: 'Remove BTC' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Remove NVDA' })).not.toBeInTheDocument();
});
