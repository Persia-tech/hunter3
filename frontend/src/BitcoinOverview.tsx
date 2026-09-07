import { Activity, ArrowDownRight, ArrowUpRight, Check, Circle, Gauge, Shield, Sparkles, TrendingDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { api } from './api';
import type { MarketTemperature } from './types';

type StageStatus = 'active' | 'inactive' | 'pending';

function formatMoney(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function formatPct(value: number | null | undefined, digits = 1) {
  if (value == null || Number.isNaN(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

function StageRow({
  stage,
  title,
  value,
  status,
  note,
}: {
  stage: string;
  title: string;
  value: string;
  status: StageStatus;
  note: string;
}) {
  return (
    <article className={`btc-stage-row ${status}`}>
      <div className="btc-stage-index">{stage}</div>
      <div className="btc-stage-copy">
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{note}</small>
      </div>
      <span className={`btc-stage-status ${status}`}>
        {status === 'active' ? <Check aria-hidden="true" /> : <Circle aria-hidden="true" />}
        {status === 'active' ? 'Active' : status === 'inactive' ? 'Inactive' : 'Pending data'}
      </span>
    </article>
  );
}

function MetricTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <article className="btc-metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </article>
  );
}

function ScoreDial({ label, value, kind }: { label: string; value: number; kind: 'opportunity' | 'overheat' }) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div className={`btc-score ${kind}`}>
      <div className="btc-score-ring" style={{ '--score': `${bounded * 3.6}deg` } as React.CSSProperties}>
        <div><strong>{Math.round(value)}</strong><span>/100</span></div>
      </div>
      <span>{label}</span>
    </div>
  );
}

export function BitcoinOverview({ onHome }: { onHome: () => void }) {
  const [data, setData] = useState<MarketTemperature>();
  const [error, setError] = useState('');

  useEffect(() => {
    api.temperatures()
      .then((items) => {
        const bitcoin = items.find((item) =>
          item.symbol.toUpperCase().includes('BTC') || item.name.toLowerCase().includes('bitcoin'),
        );
        if (!bitcoin) throw new Error('Bitcoin signal snapshot is not available yet.');
        setData(bitcoin);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const state = useMemo(() => {
    if (!data) return null;
    const stage3Bottom = data.opportunity_score >= 60;
    const below200d = data.sma_200d != null && data.current_price < data.sma_200d;
    const cheapTone = data.opportunity_score >= 60 ? 'Capitulation zone' : data.drawdown_percent <= -30 ? 'Discounted' : 'Neutral';
    return { stage3Bottom, below200d, cheapTone };
  }, [data]);

  if (error) {
    return (
      <div className="page-enter btc-overview-page">
        <section className="btc-empty-state">
          <Gauge aria-hidden="true" />
          <h1>Bitcoin overview unavailable</h1>
          <p>{error}</p>
          <button className="button secondary" onClick={onHome}>Return home</button>
        </section>
      </div>
    );
  }

  if (!data || !state) {
    return (
      <div className="page-enter btc-overview-page">
        <div className="btc-loading-card">
          <span className="btc-loading-orb" />
          <strong>Building Bitcoin state…</strong>
          <small>Loading the latest completed research signals.</small>
        </div>
      </div>
    );
  }

  return (
    <div className="page-enter btc-overview-page">
      <header className="btc-hero">
        <div className="btc-hero-topline">
          <span className="btc-mark">₿</span>
          <div><span>BITCOIN</span><small>{data.symbol}</small></div>
          <span className="btc-live-pill"><i /> Research snapshot</span>
        </div>
        <div className="btc-price-block">
          <strong>{formatMoney(data.current_price)}</strong>
          <span className={data.momentum_12m != null && data.momentum_12m < 0 ? 'negative' : 'positive'}>
            {data.momentum_12m != null && data.momentum_12m < 0 ? <ArrowDownRight /> : <ArrowUpRight />}
            {data.momentum_12m == null ? '—' : `${formatPct(data.momentum_12m * 100)} · 12M`}
          </span>
        </div>
        <div className="btc-state-card">
          <div>
            <span>MARKET STATE</span>
            <strong>{state.cheapTone}</strong>
            <small>{data.classification} · {data.trend}</small>
          </div>
          <Sparkles aria-hidden="true" />
        </div>
      </header>

      <section className="btc-score-panel" aria-label="Bitcoin scores">
        <ScoreDial label="Opportunity" value={data.opportunity_score} kind="opportunity" />
        <div className="btc-score-divider" />
        <ScoreDial label="Overheat" value={data.overheat_score} kind="overheat" />
      </section>

      <section className="btc-section">
        <div className="btc-section-heading">
          <div><span>ACCUMULATION</span><h2>Bottom stages</h2></div>
          <TrendingDown aria-hidden="true" />
        </div>
        <div className="btc-stage-stack">
          <StageRow stage="1" title="Statistical value" value="Quantile percentile" status="pending" note="Research endpoint will supply the live quantile percentile." />
          <StageRow stage="2" title="On-chain confirmation" value="MVRV percentile" status="pending" note="Live on-chain percentile will be wired into this stage." />
          <StageRow stage="3" title="Capitulation confirmation" value={`Opportunity ${Math.round(data.opportunity_score)} / 100`} status={state.stage3Bottom ? 'active' : 'inactive'} note="Active when Opportunity reaches 60 or higher." />
        </div>
      </section>

      <section className="btc-section">
        <div className="btc-section-heading">
          <div><span>DE-RISKING</span><h2>Top stages</h2></div>
          <Shield aria-hidden="true" />
        </div>
        <div className="btc-stage-stack">
          <StageRow stage="1" title="On-chain overvaluation" value="MVRV percentile" status="pending" note="Primary warning activates at the fixed research threshold." />
          <StageRow stage="2" title="Persistent weakness" value="Any-2 sustained 14d" status="pending" note="Requires rolling history; not inferred from a single snapshot." />
          <StageRow stage="3" title="Structural damage" value={data.sma_200d == null ? '200D MA unavailable' : `${formatMoney(data.sma_200d)} · 200D MA`} status={state.below200d ? 'active' : 'inactive'} note={state.below200d ? 'Price is below the 200-day moving average.' : 'Price remains above the 200-day moving average.'} />
        </div>
      </section>

      <section className="btc-section">
        <div className="btc-section-heading">
          <div><span>RAW DATA</span><h2>Indicators</h2></div>
          <Activity aria-hidden="true" />
        </div>
        <div className="btc-metric-grid">
          <MetricTile label="Weekly RSI" value={data.weekly_rsi?.toFixed(1) ?? '—'} />
          <MetricTile label="200W distance" value={formatPct(data.distance_200w_percent)} note={data.sma_200w ? `200W ${formatMoney(data.sma_200w)}` : undefined} />
          <MetricTile label="ATH drawdown" value={formatPct(data.drawdown_percent)} note={`ATH ${formatMoney(data.ath)}`} />
          <MetricTile label="200D moving avg" value={formatMoney(data.sma_200d)} />
          <MetricTile label="12M momentum" value={data.momentum_12m == null ? '—' : formatPct(data.momentum_12m * 100)} />
          <MetricTile label="Divergence" value={data.divergence || 'None'} />
        </div>
      </section>

      <section className="btc-method-note">
        <Shield aria-hidden="true" />
        <div><strong>Research first.</strong><p>Stages remain separate by design. Hunter does not collapse these signals into an opaque buy or sell score.</p></div>
      </section>

      <p className="btc-freshness">Completed snapshot · {new Date(data.as_of).toLocaleString()}</p>
    </div>
  );
}
