import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

const assets = {
  assets: [
    { symbol: 'BTC', name: 'Bitcoin', category: 'crypto' },
    { symbol: 'SPY', name: 'S&P 500', category: 'etf' },
  ],
  max_compare_assets: 10,
};

const comparison = {
  effective_end_date: '2026-08-24',
  unavailable: [],
  results: [
    {
      asset: 'BTC',
      asset_name: 'Bitcoin',
      asset_type: 'crypto',
      requested_start_date: '2021-08-24',
      requested_end_date: '2026-08-25',
      effective_end_date: '2026-08-24',
      frequency: 'monthly',
      contribution: '400.00',
      total_invested: '24280.00',
      total_units: '0.85380755',
      average_purchase_price: '28437.32',
      final_value: '67420.47',
      profit: '43140.47',
      return_pct: '177.67',
      purchase_count: 61,
      chart: [],
    },
    {
      asset: 'SPY',
      asset_name: 'S&P 500',
      asset_type: 'etf',
      requested_start_date: '2021-08-24',
      requested_end_date: '2026-08-25',
      effective_end_date: '2026-08-24',
      frequency: 'monthly',
      contribution: '400.00',
      total_invested: '24280.00',
      total_units: '43.718492',
      average_purchase_price: '555.37',
      final_value: '30120.00',
      profit: '5840.00',
      return_pct: '24.05',
      purchase_count: 61,
      chart: [],
    },
  ],
};

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.removeAttribute('data-theme');
});

describe('Mini App', () => {
  it('navigates into the calculator and selects an asset', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => assets }));
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /DCA Calculator/i }));
    await screen.findByText('Choose an asset');
    fireEvent.click(screen.getByRole('button', { name: /BTC Bitcoin/i }));

    expect(screen.getByRole('button', { name: /Continue/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /BTC Bitcoin/i })).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders a concise safe API error state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ detail: 'Market data is temporarily unavailable.' }),
      }),
    );
    render(<App />);

    await waitFor(() => expect(screen.getByText('We couldn’t complete this view')).toBeInTheDocument());
    expect(screen.getByText('Market data is temporarily unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Return home' })).toBeInTheDocument();
  });

  it('uses semantic selected navigation state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => assets }));
    render(<App />);

    await screen.findByText('DCA Calculator');
    const navigation = screen.getByRole('navigation', { name: 'Primary' });
    expect(navigation).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Home' })).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: 'Markets' }));
    expect(screen.getByRole('button', { name: 'Markets' })).toHaveAttribute('aria-current', 'page');
  });

  it('preserves Telegram dark-theme selection', () => {
    document.documentElement.dataset.theme = 'dark';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => assets }));
    render(<App />);
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('renders authoritative invested capital and every comparison result metric', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () => (url === '/api/assets' ? assets : comparison),
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    fireEvent.click(await screen.findByRole('button', { name: /BTC Bitcoin/i }));
    fireEvent.click(screen.getByRole('button', { name: /SPY S&P 500/i }));
    for (let step = 0; step < 4; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    }
    fireEvent.click(screen.getByRole('button', { name: 'Compare assets' }));

    expect(await screen.findByText('Invested per asset')).toBeInTheDocument();
    expect(screen.getByText('$24,280.00')).toBeInTheDocument();

    const bitcoin = screen.getByRole('article', { name: '1. BTC' });
    expect(within(bitcoin).getByText('0.85380755 BTC')).toBeInTheDocument();
    expect(within(bitcoin).getByText('$67,420.47')).toBeInTheDocument();
    expect(within(bitcoin).getByText('+$43,140.47')).toBeInTheDocument();
    expect(within(bitcoin).getByText('+177.67%')).toBeInTheDocument();
  });
});

describe('Hunter3 additions', () => {
  it('loads persisted Market Temperature snapshots', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve({
      ok: true,
      json: async () => url === '/api/assets' ? assets : [{symbol:'BTC-USD',name:'Bitcoin',asset_class:'crypto',as_of:'2026-01-01T00:00:00Z',current_price:100,opportunity_score:70,overheat_score:10,classification:'Strong Opportunity',trend:'Recovering',divergence:'None',weekly_rsi:30,stochastic_rsi:25,sma_200w:80,distance_200w_percent:25,ath:150,drawdown_percent:-33.3,sma_200d:90,sma_10m:95,momentum_12m:-0.1,recovery_signal:true,history_status:'Complete'}],
    }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', {name: /Market Temperature/i}));
    expect(await screen.findByText('Strong Opportunity')).toBeInTheDocument();
    expect(screen.getByText('-33.3%')).toBeInTheDocument();
    expect(screen.getByText('Recovery detected')).toBeInTheDocument();
    expect(screen.getByText('Momentum confirms improving conditions.')).toBeInTheDocument();
  });
});
