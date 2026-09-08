import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowLeftRight,
  BarChart3,
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  CircleDollarSign,
  Coins,
  Home as HomeIcon,
  LineChart,
  LoaderCircle,
  RefreshCw,
  ReceiptText,
  Search,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  ThermometerSun,
  Trash2,
  WalletCards,
  X,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { api } from './api';
import { getAssetIcon } from './assetIcons';
import { BitcoinOverview } from './BitcoinOverview';
import { OpportunityCost } from './OpportunityCost';
import { money, percent, quantity } from './format';
import { tg } from './telegram';
import type { AlertRule, Asset, DcaResult, LumpResult, MarketTemperature, Screen } from './types';

type FormValues = {
  assets: string[];
  start_date: string;
  end_date: string;
  frequency: string;
  contribution: string;
};

type CompareResult = {
  results: DcaResult[];
  unavailable: string[];
  effective_end_date: string;
};

const PERIODS = [
  ['1Y', 365],
  ['3Y', 1095],
  ['5Y', 1825],
  ['10Y', 3650],
  ['Since 2020', 0],
  ['Max', 7300],
  ['Custom', -1],
] as const;
const FREQUENCIES = ['daily', 'weekly', 'monthly'];
const AMOUNTS = ['10', '25', '50', '100'];

function AssetMark({ symbol, large = false }: { symbol: string; large?: boolean }) {
  const icon = getAssetIcon(symbol);
  return (
    <span className={`asset-monogram ${large ? 'large ' : ''}${icon.kind ?? ''}`.trim()} aria-hidden="true">
      {icon.mark}
    </span>
  );
}

function ErrorState({
  message,
  retry,
  home,
}: {
  message: string;
  retry?: () => void;
  home: () => void;
}) {
  return (
    <section className="state-panel" role="alert">
      <span className="state-icon">
        <AlertCircle aria-hidden="true" />
      </span>
      <p className="eyebrow">MARKET DATA UNAVAILABLE</p>
      <h1>We couldn’t complete this view</h1>
      <p className="state-copy">{message}</p>
      <div className="button-stack">
        {retry && (
          <button className="button primary" onClick={retry}>
            Try again
          </button>
        )}
        <button className="button secondary" onClick={home}>
          Return home
        </button>
      </div>
    </section>
  );
}

function LoadingState() {
  return (
    <section className="loading-view" aria-live="polite" aria-busy="true">
      <span className="loading-mark">
        <LoaderCircle aria-hidden="true" />
      </span>
      <p className="eyebrow">ANALYZING HISTORY</p>
      <h1>Calculating your strategy…</h1>
      <p>Retrieving completed market data and building your result.</p>
      <div className="result-skeleton" aria-hidden="true">
        <i className="skeleton skeleton-wide" />
        <div>
          <i className="skeleton" />
          <i className="skeleton" />
        </div>
        <i className="skeleton skeleton-chart" />
      </div>
    </section>
  );
}

function AssetPicker({
  assets,
  selected,
  onSelect,
  multiple = false,
  max = 10,
}: {
  assets: Asset[];
  selected: string[];
  onSelect: (symbol: string) => void;
  multiple?: boolean;
  max?: number;
}) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const categories = [...new Set(assets.map((asset) => asset.category))];
  const shown = assets.filter(
    (asset) =>
      (category === 'all' || asset.category === category) &&
      `${asset.symbol} ${asset.name}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="asset-picker">
      <label className="search-field">
        <Search aria-hidden="true" />
        <input
          aria-label="Search assets"
          placeholder="Search symbol or name"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {query && (
          <button aria-label="Clear search" onClick={() => setQuery('')}>
            <X aria-hidden="true" />
          </button>
        )}
      </label>

      {multiple && (
        <div className="selection-summary">
          <span>
            <strong>{selected.length}</strong> of {max} selected
          </span>
          <button className="button tertiary" onClick={() => selected.forEach(onSelect)}>
            Clear
          </button>
        </div>
      )}

      <div className="chip-scroll" aria-label="Asset categories">
        <button className={category === 'all' ? 'selected' : ''} onClick={() => setCategory('all')}>
          All
        </button>
        {categories.map((item) => (
          <button
            className={category === item ? 'selected' : ''}
            onClick={() => setCategory(item)}
            key={item}
          >
            {item === 'precious_metal_etf' ? 'Metals' : item}
          </button>
        ))}
      </div>

      <div className="asset-list">
        {shown.map((asset) => {
          const isSelected = selected.includes(asset.symbol);
          return (
            <button
              key={asset.symbol}
              className={`asset-row ${isSelected ? 'selected' : ''}`}
              disabled={!isSelected && multiple && selected.length >= max}
              onClick={() => onSelect(asset.symbol)}
              aria-pressed={isSelected}
            >
              <AssetMark symbol={asset.symbol} />
              <span className="asset-copy">
                <strong>{asset.symbol}</strong>
                <small>{asset.name}</small>
              </span>
              <span className="selection-indicator">
                {isSelected ? <Check aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
              </span>
            </button>
          );
        })}
        {!shown.length && (
          <div className="inline-empty">
            <Search aria-hidden="true" />
            <strong>No matching assets</strong>
            <span>Try another symbol, name, or category.</span>
          </div>
        )}
      </div>
    </div>
  );
}

const axisMoney = (value: string | number) => {
  const numeric = Number(value);
  return numeric >= 1000 ? `$${Math.round(numeric / 1000)}k` : `$${numeric}`;
};

function GrowthChart({ result }: { result: DcaResult }) {
  return (
    <section className="surface chart-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">PERFORMANCE</p>
          <h2>Portfolio growth</h2>
        </div>
        <div className="legend" aria-label="Chart legend">
          <span><i className="legend-dot value" /> Value</span>
          <span><i className="legend-dot invested" /> Invested</span>
        </div>
      </div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={result.chart} margin={{ top: 12, right: 6, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="var(--accent)" stopOpacity={0.2} />
                <stop offset="1" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="date" tickFormatter={(value) => value.slice(0, 7)} minTickGap={44} />
            <YAxis tickFormatter={axisMoney} width={42} />
            <Tooltip
              formatter={(value) => money(String(value))}
              labelFormatter={(value) => new Date(`${value}T00:00:00`).toLocaleDateString()}
              contentStyle={{
                background: 'var(--surface-raised)',
                border: '1px solid var(--border)',
                borderRadius: '12px',
              }}
            />
            <Area
              type="monotone"
              dataKey="portfolio_value"
              stroke="var(--accent)"
              fill="url(#portfolioFill)"
              strokeWidth={2.5}
              animationDuration={500}
            />
            <Line
              type="monotone"
              dataKey="contributions"
              stroke="var(--text-tertiary)"
              dot={false}
              strokeDasharray="4 5"
              strokeWidth={1.5}
              animationDuration={500}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone = '',
  featured = false,
}: {
  label: string;
  value: string;
  tone?: string;
  featured?: boolean;
}) {
  return (
    <article className={`metric-card ${featured ? 'featured' : ''}`}>
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </article>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DcaResults({ result }: { result: DcaResult }) {
  const crypto = result.asset_type === 'crypto';
  const positive = !result.return_pct.startsWith('-');
  return (
    <div className="page-enter result-page">
      <header className="result-header">
        <AssetMark symbol={result.asset} large />
        <p className="eyebrow">{result.asset_name.toUpperCase()}</p>
        <h1>{result.asset} strategy</h1>
        <p>{result.requested_start_date} – {result.effective_end_date} · {result.frequency}</p>
      </header>

      <div className="metrics-grid">
        <MetricCard label="Final value" value={money(result.final_value)} featured />
        <MetricCard label="Total invested" value={money(result.total_invested)} />
        <MetricCard
          label="Profit"
          value={money(result.profit, true)}
          tone={positive ? 'positive' : 'negative'}
        />
        <MetricCard
          label="Return"
          value={percent(result.return_pct)}
          tone={positive ? 'positive' : 'negative'}
        />
      </div>

      <section className="surface detail-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">POSITION</p>
            <h2>Investment details</h2>
          </div>
          <Coins aria-hidden="true" />
        </div>
        <DetailRow label="Units accumulated" value={quantity(result.total_units, result.asset, crypto)} />
        <DetailRow label="Purchases" value={String(result.purchase_count)} />
        <DetailRow label="Average buy price" value={money(result.average_purchase_price)} />
      </section>
      <GrowthChart result={result} />
      <p className="data-note"><Check aria-hidden="true" /> Completed data through {result.effective_end_date}</p>
    </div>
  );
}

function Inputs({
  assets,
  multiple = false,
  max = 10,
  onRun,
  title,
}: {
  assets: Asset[];
  multiple?: boolean;
  max?: number;
  onRun: (values: FormValues) => void;
  title: string;
}) {
  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [period, setPeriod] = useState('5Y');
  const [frequency, setFrequency] = useState('monthly');
  const [contribution, setContribution] = useState('50');
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const [start, setStart] = useState('');

  const choose = (symbol: string) => {
    setSelected((current) =>
      multiple
        ? current.includes(symbol)
          ? current.filter((item) => item !== symbol)
          : [...current, symbol]
        : [symbol],
    );
  };

  const dates = () => {
    if (period === 'Custom') return { start_date: start, end_date: end };
    const days = period === 'Since 2020' ? 0 : PERIODS.find(([label]) => label === period)![1];
    const startDate = days === 0 ? new Date('2020-01-01') : new Date(Date.now() - days * 86400000);
    return { start_date: startDate.toISOString().slice(0, 10), end_date: end };
  };

  const validSelection = selected.length >= (multiple ? 2 : 1);
  const stepTitles = [multiple ? 'Choose assets' : 'Choose an asset', 'Choose period', 'Frequency', 'Contribution', 'Review'];

  return (
    <div className="page-enter flow-page">
      <header className="flow-header">
        <div className="step-copy">
          <span>{step + 1}</span>
          <p>Step {step + 1} of 5</p>
        </div>
        <h1>{title}</h1>
        <div className="progress-track" aria-label={`Step ${step + 1} of 5`}>
          <i style={{ width: `${(step + 1) * 20}%` }} />
        </div>
      </header>

      <section className="step-content" key={step}>
        <h2>{stepTitles[step]}</h2>
        {step === 0 && (
          <AssetPicker assets={assets} selected={selected} onSelect={choose} multiple={multiple} max={max} />
        )}
        {step === 1 && (
          <>
            <div className="period-control">
              {PERIODS.map(([label]) => (
                <button
                  className={period === label ? 'selected' : ''}
                  onClick={() => setPeriod(label)}
                  key={label}
                >
                  {label}
                </button>
              ))}
            </div>
            {period === 'Custom' && (
              <div className="date-fields">
                <label>
                  <span>Start date</span>
                  <span className="date-input"><CalendarDays /><input type="date" max={end} value={start} onChange={(event) => setStart(event.target.value)} /></span>
                </label>
                <label>
                  <span>End date</span>
                  <span className="date-input"><CalendarDays /><input type="date" max={new Date().toISOString().slice(0, 10)} value={end} onChange={(event) => setEnd(event.target.value)} /></span>
                </label>
              </div>
            )}
          </>
        )}
        {step === 2 && (
          <div className="segmented-control">
            {FREQUENCIES.map((item) => (
              <button className={frequency === item ? 'selected' : ''} onClick={() => setFrequency(item)} key={item}>
                {item}
              </button>
            ))}
          </div>
        )}
        {step === 3 && (
          <>
            <p className="supporting-copy">Amount invested each {frequency === 'daily' ? 'day' : frequency === 'weekly' ? 'week' : 'month'}.</p>
            <div className="amount-presets">
              {AMOUNTS.map((amount) => (
                <button className={contribution === amount ? 'selected' : ''} onClick={() => setContribution(amount)} key={amount}>
                  ${amount}
                </button>
              ))}
            </div>
            <label className="currency-field">
              <span>$</span>
              <input
                inputMode="decimal"
                aria-label="Custom contribution"
                value={contribution}
                onChange={(event) => setContribution(event.target.value)}
              />
              <small>USD</small>
            </label>
          </>
        )}
        {step === 4 && (
          <>
            <section className="surface review-panel">
              <DetailRow label={multiple ? 'Assets' : 'Asset'} value={selected.join(', ')} />
              <DetailRow label="Period" value={period} />
              <DetailRow label="Frequency" value={frequency} />
              <DetailRow label="Contribution" value={money(contribution)} />
            </section>
            {multiple && (
              <div className="fairness-note">
                <SlidersHorizontal aria-hidden="true" />
                <span><strong>Fair by design</strong>Equal capital, schedule, and effective period.</span>
              </div>
            )}
          </>
        )}
      </section>

      <footer className="flow-actions">
        {step > 0 && (
          <button className="button secondary back-button" onClick={() => setStep(step - 1)}>
            Back
          </button>
        )}
        <button
          className="button primary"
          disabled={(step === 0 && !validSelection) || (step === 1 && period === 'Custom' && (!start || !end))}
          onClick={() => (step < 4 ? setStep(step + 1) : onRun({ assets: selected, ...dates(), frequency, contribution }))}
        >
          {step === 4 ? (multiple ? 'Compare assets' : 'Calculate strategy') : 'Continue'}
          <ChevronRight aria-hidden="true" />
        </button>
      </footer>
    </div>
  );
}

function CompareResults({ data }: { data: CompareResult }) {
  const context = data.results[0];
  return (
    <div className="page-enter result-page">
      <header className="screen-header">
        <p className="eyebrow">FAIR COMPARISON</p>
        <h1>Compare Assets</h1>
        <p>
          Equal capital · Same schedule · Through {data.effective_end_date}
        </p>
      </header>
      <section className="comparison-context" aria-label="Comparison assumptions">
        <span>
          <small>COMMON PERIOD</small>
          <strong>{context.requested_start_date} – {context.requested_end_date}</strong>
        </span>
        <span>
          <small>FREQUENCY</small>
          <strong>{context.frequency}</strong>
        </span>
        <span>
          <small>EFFECTIVE END</small>
          <strong>{data.effective_end_date}</strong>
        </span>
      </section>
      <p className="invested-summary">
        <span>Invested per asset</span>
        <strong>{money(context.total_invested)}</strong>
      </p>
      <div className="ranking-list">
        {data.results.map((result, index) => (
          <article
            aria-label={`${index + 1}. ${result.asset}`}
            className={`ranking-card ${index === 0 ? 'leader' : ''}`}
            key={result.asset}
          >
            <div className="ranking-topline">
              <span className="rank-number">{index + 1}</span>
              <AssetMark symbol={result.asset} />
              <span className="asset-copy"><strong>{result.asset}</strong><small>{result.asset_name}</small></span>
              <strong className={result.return_pct.startsWith('-') ? 'negative' : 'positive'}>{percent(result.return_pct)}</strong>
            </div>
            <div className="ranking-metrics">
              <span><small>Accumulated</small><strong>{quantity(result.total_units, result.asset, result.asset_type === 'crypto')}</strong></span>
              <span><small>Final value</small><strong>{money(result.final_value)}</strong></span>
              <span>
                <small>Profit</small>
                <strong className={result.profit.startsWith('-') ? 'negative' : 'positive'}>
                  {money(result.profit, true)}
                </strong>
              </span>
            </div>
          </article>
        ))}
      </div>
      {data.unavailable.length > 0 && (
        <section className="surface unavailable-panel">
          <AlertCircle aria-hidden="true" />
          <span><strong>Unavailable</strong><small>{data.unavailable.join(' · ')} · Not included in ranking</small></span>
        </section>
      )}
    </div>
  );
}

function StrategyCard({
  name,
  investedLabel,
  unitsLabel,
  asset,
  data,
  winner,
}: {
  name: string;
  investedLabel: string;
  unitsLabel: string;
  asset: string;
  data: { total_invested: string; total_units: string; final_value: string; profit: string; return_pct: string };
  winner: boolean;
}) {
  const positive = !data.return_pct.startsWith('-');
  return (
    <article className={`strategy-card ${winner ? 'winner-strategy' : ''}`}>
      <div className="strategy-heading">
        <span className="strategy-icon">{name === 'DCA' ? <LineChart /> : <CircleDollarSign />}</span>
        <div><h2>{name}</h2>{winner && <small>Leading strategy</small>}</div>
      </div>
      <div className="strategy-value">
        <span>Final value</span>
        <strong>{money(data.final_value)}</strong>
      </div>
      <DetailRow label={investedLabel} value={money(data.total_invested)} />
      <DetailRow label={unitsLabel} value={quantity(data.total_units, asset, asset === 'BTC')} />
      <DetailRow label="Profit" value={money(data.profit, true)} />
      <div className={`strategy-return ${positive ? 'positive' : 'negative'}`}>{percent(data.return_pct)} return</div>
    </article>
  );
}

function LumpResults({ result }: { result: LumpResult }) {
  return (
    <div className="page-enter result-page flagship-page">
      <header className="result-header">
        <p className="eyebrow">STRATEGY COMPARISON</p>
        <h1>DCA vs Lump Sum</h1>
        <p>{result.asset_name} · Through {result.effective_end_date}</p>
      </header>
      <section className="capital-hero">
        <WalletCards aria-hidden="true" />
        <span>Total capital</span>
        <strong>{money(result.total_capital)}</strong>
        <small>Identical capital across both strategies</small>
      </section>
      <div className="strategy-list">
        <StrategyCard
          name="DCA"
          investedLabel="Invested"
          unitsLabel="Accumulated units"
          asset={result.asset}
          data={result.dca}
          winner={result.winner === 'DCA'}
        />
        <StrategyCard
          name="Lump Sum"
          investedLabel="Initial investment"
          unitsLabel="Units bought"
          asset={result.asset}
          data={result.lump_sum}
          winner={result.winner === 'LUMP_SUM'}
        />
      </div>
      <section className="winner-panel">
        <Sparkles aria-hidden="true" />
        <div><span>Winner</span><h2>{result.winner.replace('_', ' ')}</h2></div>
        <p><strong>{money(result.value_difference)}</strong><span>difference in final value</span></p>
      </section>
      <GrowthChart result={result.dca} />
    </div>
  );
}

function Markets({ onHome }: { onHome: () => void }) {
  const [data, setData] = useState<{ prices: { symbol: string; name: string; price: string }[]; unavailable: string[]; fetched_at: string }>();
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(() => {
    setError('');
    setRefreshing(true);
    api.prices().then(setData).catch((reason) => setError(reason.message)).finally(() => setRefreshing(false));
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  if (error) return <ErrorState message="We couldn’t load the latest completed market snapshot." retry={load} home={onHome} />;
  return (
    <div className="page-enter markets-page">
      <header className="screen-header action-header">
        <div><p className="eyebrow">MARKETS</p><h1>Current prices</h1><p>A cached market snapshot.</p></div>
        <button className="icon-button" onClick={load} aria-label="Refresh prices" disabled={refreshing}>
          <RefreshCw className={refreshing ? 'spinning' : ''} aria-hidden="true" />
        </button>
      </header>
      {!data ? <LoadingState /> : (
        <>
          <div className="market-list">
            {data.prices.map((price) => (
              <article className="market-row" key={price.symbol}>
                <AssetMark symbol={price.symbol} />
                <span className="asset-copy"><strong>{price.symbol}</strong><small>{price.name}</small></span>
                <strong>{money(price.price)}</strong>
              </article>
            ))}
          </div>
          <p className="data-note"><Check aria-hidden="true" /> Snapshot {new Date(data.fetched_at).toLocaleString()}</p>
        </>
      )}
    </div>
  );
}

function Temperature({ onHome }: { onHome: () => void }) {
  const [data, setData] = useState<MarketTemperature[]>();
  const [error, setError] = useState('');
  useEffect(() => { api.temperatures().then(setData).catch((reason) => setError(reason.message)); }, []);
  if (error) return <ErrorState message={error} home={onHome} />;
  if (!data) return <LoadingState />;
  return <div className="page-enter markets-page"><header className="screen-header"><p className="eyebrow">MARKET TEMPERATURE</p><h1>Long-term conditions</h1><p>Three distinct signals, designed for patient decisions.</p></header><div className="temperature-list">{data.map((item) => <article className="temperature-card" key={item.symbol}><div className="temperature-heading"><AssetMark symbol={item.symbol}/><span className="asset-copy"><strong>{item.symbol}</strong><small>{item.name}</small></span><span className="classification">{item.classification}</span></div><div className="temperature-scores"><span className="opportunity"><small>Opportunity</small><strong>{item.opportunity_score}<em>/100</em></strong></span><span className="overheat"><small>Overheat</small><strong>{item.overheat_score}<em>/100</em></strong></span></div><div className="signal-summary"><span><small>Drawdown zone</small><strong>{item.drawdown_percent.toFixed(1)}%</strong></span><span><small>Trend</small><strong>{item.trend}</strong></span></div><details><summary>Technical details</summary><div className="technical-grid"><span>Weekly RSI <strong>{item.weekly_rsi?.toFixed(1) ?? '—'}</strong></span><span>Stochastic RSI <strong>{item.stochastic_rsi?.toFixed(1) ?? '—'}</strong></span><span>200W distance <strong>{item.distance_200w_percent?.toFixed(1) ?? '—'}%</strong></span><span>12M momentum <strong>{item.momentum_12m == null ? '—' : percent(String(item.momentum_12m * 100))}</strong></span><span>Divergence <strong>{item.divergence}</strong></span><span>Recovery <strong>{item.recovery_signal ? 'Detected' : 'Not detected'}</strong></span></div></details><p className="freshness">Updated {new Date(item.as_of).toLocaleString()} · {item.history_status} history</p></article>)}</div>{!data.length && <section className="surface premium-empty"><ThermometerSun aria-hidden="true"/><h2>No market snapshot yet</h2><p>Signals will appear after the next market update.</p><button className="button secondary" onClick={onHome}>Return home</button></section>}</div>;
}

function Alerts({ onHome }: { onHome: () => void }) {
  const presets = [
    {label:'BTC quantile enters ≤10',metric:'bitcoin_quantile_percentile',operator:'below_or_equal',value:10},
    {label:'BTC MVRV percentile enters ≤20',metric:'bitcoin_mvrv_percentile',operator:'below_or_equal',value:20},
    {label:'BTC opportunity enters ≥60',metric:'opportunity_score',operator:'above_or_equal',value:60},
    {label:'BTC MVRV percentile enters ≥90',metric:'bitcoin_mvrv_percentile',operator:'above_or_equal',value:90},
    {label:'BTC Top Stage 2 becomes active',metric:'bitcoin_top_stage2_active',operator:'equal',value:1},
    {label:'BTC crosses below 200D MA',metric:'bitcoin_below_200d_ma',operator:'equal',value:1},
    {label:'BTC crosses below 200W MA',metric:'bitcoin_below_200w_ma',operator:'equal',value:1},
  ];
  const [rules, setRules] = useState<AlertRule[]>();
  const [error, setError] = useState('');
  const [presetIndex, setPresetIndex] = useState(2);
  const load = useCallback(() => api.alerts().then(setRules).catch((reason) => setError(reason.message)), []);
  useEffect(() => {
    void load();
  }, [load]);
  const create = () => { const preset=presets[presetIndex]; return api.createAlert({scope_type:'symbol',scope_value:'BTC-USD',metric:preset.metric,operator:preset.operator,numeric_value:preset.value,notify_on_enter:true,notify_on_exit:false,cooldown_minutes:60,delivery_channel:'telegram'}).then(load).catch((reason) => setError(reason.message)); };
  const describe = (rule: AlertRule) => presets.find((preset) => preset.metric===rule.metric && preset.operator===rule.operator && preset.value===rule.numeric_value)?.label ?? `${rule.metric} ${rule.operator} ${rule.numeric_value ?? rule.text_value}`;
  if (error) return <ErrorState message={error} retry={() => {setError('');load();}} home={onHome}/>;
  if (!rules) return <LoadingState/>;
  return <div className="page-enter markets-page"><header className="screen-header"><p className="eyebrow">ALERTS</p><h1>Stay informed, calmly</h1><p>Hunter sends a Telegram message only when your signal changes.</p></header><section className="surface alert-builder"><label>Bitcoin condition<select aria-label="Bitcoin alert condition" value={presetIndex} onChange={(event)=>setPresetIndex(Number(event.target.value))}>{presets.map((preset,index)=><option key={preset.label} value={index}>{preset.label}</option>)}</select></label><button className="button primary" onClick={create}>Create alert</button></section>{rules.length ? <div className="alert-list">{rules.map((rule)=><article className="alert-card" key={rule.id}><span className={`status-dot ${rule.enabled?'enabled':'paused'}`} aria-label={rule.enabled?'Enabled':'Paused'} /><span className="asset-copy"><strong>{rule.scope_value ?? 'All assets'}</strong><small>{describe(rule)}</small></span><button className="button tertiary" onClick={()=>api.setAlertEnabled(rule.id,!rule.enabled).then(load)}>{rule.enabled?'Pause':'Enable'}</button><button className="delete-button" aria-label={`Delete alert for ${rule.scope_value ?? 'all assets'}`} onClick={()=>api.deleteAlert(rule.id).then(load)}><Trash2 aria-hidden="true"/></button></article>)}</div> : <section className="surface premium-empty"><Bell aria-hidden="true"/><h2>No alerts yet</h2><p>Create a signal alert and Hunter will keep watch for you.</p></section>}</div>;
}

const FEATURES = [
  { screen: 'opportunity' as Screen, title: 'Opportunity Cost', description: 'What if you invested instead?', icon: ReceiptText, tone: 'green' },
  { screen: 'dca' as Screen, title: 'DCA Calculator', description: 'Build a consistent investing plan', icon: TrendingUp, tone: 'blue' },
  { screen: 'compare' as Screen, title: 'Compare Assets', description: 'Compare long-term outcomes', icon: ArrowLeftRight, tone: 'indigo' },
  { screen: 'lump' as Screen, title: 'DCA vs Lump Sum', description: 'Compare two capital strategies', icon: WalletCards, tone: 'slate' },
  { screen: 'markets' as Screen, title: 'Market Prices', description: 'See the latest market snapshot', icon: BarChart3, tone: 'graphite' },
];

function Home({ go }: { go: (screen: Screen) => void }) {
  const [signal, setSignal] = useState<MarketTemperature>();
  useEffect(() => { api.temperatures().then((items) => Array.isArray(items) && setSignal(items[0])).catch(() => undefined); }, []);
  return (
    <div className="page-enter home-page">
      <header className="home-hero">
        <div className="product-mark"><LineChart aria-hidden="true" /><span>HUNTER 3</span></div>
        <h1>Invest with a longer view.</h1>
        <p>Long-term investing intelligence.</p>
      </header>
      <button className="bitcoin-home-card" onClick={() => go('bitcoin')}>
        <span className="btc-mark">₿</span>
        <span className="bitcoin-home-card-copy"><small>BITCOIN RESEARCH</small><strong>BTC Current State</strong><span>Bottom stages · Top stages · Raw indicators</span></span>
        <ChevronRight aria-hidden="true" />
      </button>
      <button className="temperature-hero" onClick={() => go('temperature')}>
        <span className="hero-icon"><ThermometerSun aria-hidden="true" /></span><span className="hero-kicker">MARKET TEMPERATURE</span>
        <strong>{signal ? `${signal.classification} · ${signal.trend}` : 'Conditions, made clear'}</strong>
        <span className="hero-copy">{signal ? <><b>Opportunity {signal.opportunity_score}</b><b>Overheat {signal.overheat_score}</b></> : 'See long-term market conditions'}</span>
        <span className="hero-link">View signals <ChevronRight aria-hidden="true" /></span>
      </button>
      <section className="feature-grid" aria-label="Explore DCA tools">
        {FEATURES.map(({ screen, title, description, icon: Icon, tone }) => (
          <button className={`feature-card ${tone}`} key={screen} onClick={() => go(screen)}>
            <span className="feature-icon"><Icon aria-hidden="true" /></span>
            <span className="feature-copy"><strong>{title}</strong><small>{description}</small></span>
            <ChevronRight className="feature-chevron" aria-hidden="true" />
          </button>
        ))}
      </section>
      <button className="utility-card" onClick={() => go('alerts')}><span className="feature-icon"><Bell aria-hidden="true"/></span><span className="feature-copy"><strong>Alerts</strong><small>Get notified when signals change</small></span><ChevronRight aria-hidden="true"/></button>
      <p className="disclaimer">Historical outcomes are informational, not investment advice.</p>
    </div>
  );
}

const NAV_ITEMS = [
  { screen: 'home' as Screen, label: 'Home', icon: HomeIcon },
  { screen: 'bitcoin' as Screen, label: 'Bitcoin', icon: LineChart },
  { screen: 'dca' as Screen, label: 'Calculate', icon: TrendingUp },
  { screen: 'compare' as Screen, label: 'Compare', icon: ArrowLeftRight },
  { screen: 'opportunity' as Screen, label: 'Opportunity', icon: ReceiptText },
  { screen: 'markets' as Screen, label: 'Markets', icon: BarChart3 },
  { screen: 'temperature' as Screen, label: 'Signals', icon: ThermometerSun },
  { screen: 'alerts' as Screen, label: 'Alerts', icon: Bell },
];

export function App() {
  const [screen, setScreen] = useState<Screen>('home');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [max, setMax] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<DcaResult | LumpResult | CompareResult>();

  useEffect(() => {
    api.assets().then((response) => {
      setAssets(response.assets);
      setMax(response.max_compare_assets);
    }).catch((reason) => setError(reason.message));
  }, []);

  const go = useCallback((nextScreen: Screen) => {
    setScreen(nextScreen);
    setResult(undefined);
    setError('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const back = () => go('home');
    if (screen !== 'home') tg?.BackButton.show();
    else tg?.BackButton.hide();
    tg?.BackButton.onClick(back);
    return () => tg?.BackButton.offClick(back);
  }, [go, screen]);

  const run = (values: FormValues) => {
    setLoading(true);
    setError('');
    const body = {
      asset: values.assets[0],
      start_date: values.start_date,
      end_date: values.end_date,
      frequency: values.frequency,
      contribution: values.contribution,
    };
    const call = screen === 'compare'
      ? api.compare({ ...body, assets: values.assets })
      : screen === 'lump'
        ? api.lump(body)
        : api.dca(body);
    call
      .then((response) => setResult(response))
      .catch((reason) => setError(reason.message))
      .finally(() => setLoading(false));
  };

  let content;
  if (loading) content = <LoadingState />;
  else if (error) content = <ErrorState message={error} retry={() => { setError(''); setResult(undefined); }} home={() => go('home')} />;
  else if (screen === 'home') content = <Home go={go} />;
  else if (screen === 'bitcoin') content = <BitcoinOverview onHome={() => go('home')} />;
  else if (screen === 'markets') content = <Markets onHome={() => go('home')} />;
  else if (screen === 'temperature') content = <Temperature onHome={() => go('home')} />;
  else if (screen === 'alerts') content = <Alerts onHome={() => go('home')} />;
  else if (screen === 'opportunity') content = <OpportunityCost assets={assets} />;
  else if (result && screen === 'compare') content = <CompareResults data={result as CompareResult} />;
  else if (result && screen === 'lump') content = <LumpResults result={result as LumpResult} />;
  else if (result) content = <DcaResults result={result as DcaResult} />;
  else content = <Inputs title={screen === 'compare' ? 'Compare assets' : screen === 'lump' ? 'DCA vs Lump Sum' : 'DCA Calculator'} assets={assets} multiple={screen === 'compare'} max={max} onRun={run} />;

  return (
    <main className="app-shell">
      <div className="content-container">{content}</div>
      <nav className="bottom-nav" aria-label="Primary">
        <div className="nav-inner">
          {NAV_ITEMS.map(({ screen: itemScreen, label, icon: Icon }) => (
            <button className={screen === itemScreen ? 'selected' : ''} onClick={() => go(itemScreen)} key={itemScreen} aria-current={screen === itemScreen ? 'page' : undefined}>
              <span className="nav-icon"><Icon aria-hidden="true" /></span>
              <span>{label}</span>
            </button>
          ))}
        </div>
      </nav>
    </main>
  );
}
