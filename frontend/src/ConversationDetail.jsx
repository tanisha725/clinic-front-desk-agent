import { useEffect, useState } from 'react'
import { getConversation, getConversations, runAgent } from './api.js'
import { REASONS, STATE_TONES } from './labels.js'

// search_slots(doctor_id="dr_rao", date="2026-10-03")
function callText(event) {
  const args = Object.entries(event.arguments).map(([key, value]) => `${key}="${value}"`)
  return `(${args.join(', ')})`
}

// One line saying what the tool returned. Everything the agent later says comes from here.
function resultText(event) {
  const result = event.result
  if (!result.ok) return `✗ ${result.error.code}: ${result.error.message}`
  if (event.name === 'search_slots') {
    if (result.slots.length === 0) return `→ no slots (${result.reason})`
    const shown = result.slots.slice(0, 6).join(', ')
    return `→ ${result.slots.length} slots: ${shown}${result.slots.length > 6 ? ', …' : ''}`
  }
  if (event.name === 'lookup_patient') {
    const names = result.candidates.map((c) => `${c.id} ${c.name}`).join(', ')
    return `→ ${result.count} candidate${result.count === 1 ? '' : 's'}${names ? ': ' + names : ''}`
  }
  if (event.name === 'escalate_to_human') return `→ handed off (${result.reason})`
  const a = result.appointment
  return `→ ${a.id} ${a.status}: ${a.doctor_id} ${a.date} ${a.start}`
}

function Transcript({ record }) {
  const { result } = record
  const changed = ['booked', 'rescheduled', 'cancelled'].includes(result.terminal_state)
  return (
    <section className="card">
      <h2>Transcript and tool calls</h2>
      {record.transcript.map((event, index) => (
        <div className="line" key={index}>
          <div className="eyebrow line-role">{event.role}</div>
          {event.role === 'tool' ? (
            <div className="bubble tool mono">
              <strong>{event.name}</strong>
              {callText(event)}
              <div>{resultText(event)}</div>
            </div>
          ) : (
            <div className={'bubble ' + event.role}>{event.text}</div>
          )}
        </div>
      ))}
      <div className="line">
        <div className="line-role" />
        <div className={'banner ' + (changed ? 'green' : 'red')}>
          {changed
            ? `Appointment ${result.appointment_id} ${result.terminal_state}.`
            : 'Flow stopped. No appointment was created or changed.'}
        </div>
      </div>
    </section>
  )
}

function Outcome({ record }) {
  const { result, fingerprints } = record
  const stable = new Set(fingerprints).size === 1
  const rows = [
    ['terminal_state', result.terminal_state],
    ['escalation_reason', String(result.escalation_reason)],
    ['patient_id', String(result.patient_id)],
    ['appointment_id', String(result.appointment_id)],
    ['tool_calls', result.tool_calls.length],
    ['turns', result.metrics.turns],
    ['tokens', result.metrics.tokens.toLocaleString()],
    ['latency', `${result.metrics.latency_ms} ms`],
    ['reader', record.reader],
  ]
  return (
    <section className="card">
      <h2>Outcome</h2>
      {rows.map(([key, value]) => (
        <div className="outcome-row" key={key}>
          <span className="muted">{key}</span>
          <span className="mono strong">{value}</span>
        </div>
      ))}
      <div className="eyebrow determinism">Determinism</div>
      <div className="outcome-row">
        <span className="muted">
          Same terminal state across {fingerprints.length} run{fingerprints.length === 1 ? '' : 's'}.
        </span>
        <span className={'badge ' + (stable ? 'green' : 'red')}>{stable ? 'STABLE' : 'UNSTABLE'}</span>
      </div>
    </section>
  )
}

export default function ConversationDetail({ conversationId, onSelect }) {
  const [list, setList] = useState([])
  const [record, setRecord] = useState(null)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getConversations()
      .then((conversations) => {
        setList(conversations)
        if (!conversationId && conversations.length) onSelect(conversations[0].conversation_id)
      })
      .catch((e) => setError(e.message))
  }, [conversationId, onSelect])

  useEffect(() => {
    if (!conversationId) return
    getConversation(conversationId)
      .then(setRecord)
      .catch((e) => setError(e.message))
  }, [conversationId])

  // Runs the same conversation three times, the way the grader does.
  async function runThreeTimes(id, today, turns) {
    setBusy(true)
    setError('')
    try {
      for (let i = 0; i < 3; i++) await runAgent(id, today, turns)
      setRecord(await getConversation(id))
      setList(await getConversations())
      onSelect(id)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  function runDraft() {
    const turns = draft.split('\n').map((line) => line.trim()).filter(Boolean)
    if (turns.length) runThreeTimes(`ui_${Date.now()}`, '2026-10-01', turns)
  }

  const result = record?.result
  const reason = result && REASONS[result.escalation_reason]

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Conversation {conversationId || ''}</h1>
          <p className="muted">Sunrise Clinic, Dehradun{record ? ` — ${record.logged_at}` : ''}</p>
        </div>
        <div className="header-actions">
          <select
            className="button"
            aria-label="Choose a conversation"
            value={conversationId || ''}
            onChange={(e) => onSelect(e.target.value)}
          >
            {list.length === 0 && <option value="">No conversations yet</option>}
            {list.map((c) => (
              <option key={c.conversation_id} value={c.conversation_id}>
                {c.conversation_id} · {c.terminal_state}
              </option>
            ))}
          </select>
          {record && (
            <button
              className="button"
              disabled={busy}
              onClick={() => runThreeTimes(record.conversation_id, record.today, record.turns)}
            >
              {busy ? 'Running…' : 'Run 3 times'}
            </button>
          )}
          {result && (
            <span className={'badge ' + STATE_TONES[result.terminal_state]}>
              {result.terminal_state.toUpperCase()}
              {reason ? ` — ${reason.label}` : ''}
            </span>
          )}
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      {record ? (
        <div className="detail">
          <Transcript record={record} />
          <Outcome record={record} />
        </div>
      ) : (
        <p className="muted">No conversation selected. Run one below, or replay the samples from the Handoff Queue.</p>
      )}

      <section className="card try">
        <h2>Try a call</h2>
        <p className="muted">One caller turn per line. today is 2026-10-01 (Thursday).</p>
        <textarea
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={'Dr. Rao ke saath Saturday subah 10 baje.\nTarun Bisht, 9812200663.'}
        />
        <button className="button primary" onClick={runDraft} disabled={busy || !draft.trim()}>
          {busy ? 'Running…' : 'Run'}
        </button>
      </section>
    </>
  )
}
