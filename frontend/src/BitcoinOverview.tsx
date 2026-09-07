import { Activity, ArrowDownRight, ArrowUpRight, Check, Circle, Gauge, Shield, Sparkles, TrendingDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { api } from './api';
import type { BitcoinResearchState, MarketTemperature } from './types';

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

function formatPercentile(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)} / 100`;
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
  const [research, setResearch] = useState<BitcoinResearchState>();
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.temperatures(), api.bitcoinResearchState()])
      .then(([items, researchState]) => {
        const bitcoin = items.find((item) =>
          item.symbol.toUpperCase().includes('BTC') || item.name.toLowerCase().includes('bitcoin'),
        );
        if (!bitcoin) throw new Error('Bitcoin signal snapshot is not available yet.');
        setData(bitcoin);
        setResearch(researchState);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const state = useMemo(() => {
    if (!data) return null;
    const quantilePercentile = research?.quantile?.percentile ?? null;
    const mvrvPercentile = research?.mvrv?.percentile ?? null;
    const stage1Bottom = quantilePercentile != null && quantilePercentile <= 10;
    const stage2Bottom = stage1Bottom && mvrvPercentile != null && mvrvPercentile <= 20;
    const stage3Bottom = data.opportunity_score >= 60;
    const stage1Top = mvrvPercentile != null && mvrvPercentile >= 90;
    const stage2Top = research?.top_stage2?.active ?? false;
    const below200d = data.sma_200d != null && data.current_price < data.sma_200d;
    const cheapTone = stage2Bottom
      ? 'Deep value confirmed'
      : stage1Bottom
        ? 'Statistically cheap'
        : data.opportunity_score >= 60
          ? 'Capitulation zone'
          : data.drawdown_percent <= -30
            ? 'Discounted'
            : 'Neutral';
    const interpretation = stage2Top
      ? 'Persistent weakness has confirmed after an MVRV overvaluation warning. The structural 200-day trend remains a separate final layer.'
      : stage2Bottom
        ? 'Statistical value and on-chain confirmation are aligned. Technical capitulation confirmation remains separate.'
        : stage1Bottom
          ? 'Valuation is statistically low, but on-chain and capitulation confirmation are not active yet.'
          : stage1Top
            ? 'On-chain valuation is elevated. Persistent weakness has not confirmed yet.'
            : 'No extreme accumulation or de-risking confirmation is active. Signals remain mixed or neutral.';
    return { stage1Bottom, stage2Bottom, stage3Bottom, stage1Top, stage2Top, below200d, cheapTone, interpretation };
  }, [data, research]);

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

  if (!data || !state || !research) {
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

  const quantile = research.quantile;
  const mvrv = research.mvrv;
  const topStage2 = research.top_stage2;
  const topStage2Status: StageStatus = topStage2
    ? (topStage2.active ? 'active' : 'inactive')
    : (research.top_stage2_error ? 'pending' : 'inactive');
  const topStage2Value = topStage2
    ? topStage2.active && topStage2.confirmation_date
      ? `Confirmed ${topStage2.confirmation_date}`
      : topStage2.warning_date && topStage2.warning_age_days != null && topStage2.warning_age_days <= 180
        ? `Any-2 streak ${topStage2.current_any2_streak_days} / 14`
        : 'No recent confirmation window'
    : 'Any-2 sustained 14d';
  const topStage2Note = topStage2?.reason
    ?? research.top_stage2_error
    ?? 'Waiting for sufficient live history to evaluate the fixed persistence rule.';

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
            <small>{state.interpretation}</small>
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
          <StageRow
            stage="1"
            title="Statistical value"
            value={quantile ? `Quantile ${formatPercentile(quantile.percentile)}` : 'Quantile unavailable'}
            status={quantile ? (state.stage1Bottom ? 'active' : 'inactive') : 'pending'}
            note={state.stage1Bottom ? 'Historically cheap valuation. Active at percentile 10 or lower.' : 'Not in the historically cheap quantile zone.'}
          />
          <StageRow
            stage="2"
            title="On-chain confirmation"
            value={mvrv ? `MVRV ${mvrv.value.toFixed(2)} · pct ${mvrv.percentile.toFixed(1)}` : 'MVRV unavailable'}
            status={mvrv && quantile ? (state.stage2Bottom ? 'active' : 'inactive') : 'pending'}
            note={state.stage2Bottom ? 'Statistical value and MVRV are both in their low historical zones.' : 'Requires Quantile ≤10 and MVRV historical percentile ≤20.'}
          />
          <StageRow
            stage="3"
            title="Capitulation confirmation"
            value={`Opportunity ${Math.round(data.opportunity_score)} / 100`}
            status={state.stage3Bottom ? 'active' : 'inactive'}
            note={state.stage3Bottom ? 'Technical capitulation confirmation is active.' : 'Activates when Opportunity reaches 60 or higher.'}
          />
        </div>
      </section>

      <section className="btc-section">
        <div className="btc-section-heading">
          <div><span>DE-RISKING</span><h2>Top stages</h2></div>
          <Shield aria-hidden="true" />
        </div>
        <div className="btc-stage-stack">
          <StageRow
            stage="1"
            title="On-chain overvaluation"
            value={mvrv ? `MVRV ${mvrv.value.toFixed(2)} · pct ${mvrv.percentile.toFixed(1)}` : 'MVRV unavailable'}
            status={mvrv ? (state.stage1Top ? 'active' : 'inactive') : 'pending'}
            note={state.stage1Top ? 'Primary overvaluation warning is active.' : 'Primary warning activates at MVRV historical percentile 90 or higher.'}
          />
          <StageRow
            stage="2"
            title="Persistent weakness"
            value={topStage2Value}
            status={topStage2Status}
            note={topStage2Note}
          />
          <StageRow
            stage="3"
            title="Structural damage"
            value={data.sma_200d == null ? '200D MA unavailable' : `${formatMoney(data.sma_200d)} · 200D MA`}
            status={state.below200d ? 'active' : 'inactive'}
            note={state.below200d ? 'Price is below the 200-day moving average.' : 'Price remains above the 200-day moving average.'}
          />
        </div>
      </section>

      <section className="btc-section">
        <div className="btc-section-heading">
          <div><span>RAW DATA</span><h2>Indicators</h2></div>
          <Activity aria-hidden="true" />
        </div>
        <div className="btc-metric-grid">
          <MetricTile label="Quantile percentile" value={quantile ? formatPercentile(quantile.percentile) : '—'} note={quantile ? `Model date ${quantile.as_of}` : research.quantile_error} />
          <MetricTile label="MVRV" value={mvrv ? mvrv.value.toFixed(3) : '—'} note={mvrv ? `${mvrv.freshness} · ${mvrv.as_of}` : research.mvrv_error} />
          <MetricTile label="MVRV percentile" value={mvrv ? formatPercentile(mvrv.percentile) : '—'} note={mvrv ? `${mvrv.history_observations.toLocaleString()} observations` : undefined} />
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
