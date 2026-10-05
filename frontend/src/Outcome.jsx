function Row({ name, value }) {
  return (
    <div className="outcome-row">
      <span className="muted">{name}</span>
      <span className="mono strong">{String(value)}</span>
    </div>
  )
}

// 4200 -> "4.2 s", 3 -> "3 ms"
function latency(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`
}

// The machine-readable result: the same fields POST /agent/run returns.
export default function Outcome({ record }) {
  const { result, fingerprints } = record
  const stable = new Set(fingerprints).size === 1
  const runs = fingerprints.length
  return (
    <section className="card">
      <h2>Outcome</h2>
      <p className="muted small">The exact fields the API returned for this call.</p>

      <Row name="terminal_state" value={result.terminal_state} />
      <Row name="escalation_reason" value={result.escalation_reason} />
      <Row name="patient_id" value={result.patient_id} />
      <Row name="appointment_id" value={result.appointment_id} />
      <Row name="tool_calls" value={result.tool_calls.length} />
      <Row name="turns" value={result.metrics.turns} />
      <Row name="tokens" value={result.metrics.tokens.toLocaleString()} />
      <Row name="latency" value={latency(result.metrics.latency_ms)} />

      <div className="eyebrow determinism">Determinism</div>
      <div className="outcome-row">
        <span className="muted">
          {runs === 1
            ? 'Run once so far.'
            : `${stable ? 'Same' : 'Different'} terminal state across ${runs} runs.`}
        </span>
        <span className={'badge ' + (stable ? 'green' : 'red')}>{stable ? 'STABLE' : 'UNSTABLE'}</span>
      </div>
    </section>
  )
}
