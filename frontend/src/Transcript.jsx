import { REASONS, STATES, TOOL_TITLES } from './labels.js'

// search_slots(doctor_id="dr_rao", date="2026-10-03")
function rawCall(event) {
  const args = Object.entries(event.arguments).map(([key, value]) => `${key}="${value}"`)
  return `${event.name}(${args.join(', ')})`
}

// One line saying what the tool returned. Everything the agent says next comes from here.
function resultText(event) {
  const result = event.result
  if (!result.ok) return `Refused by the tool: ${result.error.message}`
  if (event.name === 'search_slots') {
    if (result.slots.length === 0) return `No slots (${result.reason.replaceAll('_', ' ')})`
    const shown = result.slots.slice(0, 6).join(', ')
    return `${result.slots.length} free slots: ${shown}${result.slots.length > 6 ? ', …' : ''}`
  }
  if (event.name === 'lookup_patient') {
    if (result.count === 0) return 'No patient found'
    const names = result.candidates.map((c) => `${c.name} (${c.id})`).join(', ')
    return `${result.count} match${result.count === 1 ? '' : 'es'}: ${names}`
  }
  if (event.name === 'escalate_to_human') return `Added to the handoff queue (${result.reason})`
  const a = result.appointment
  return `${a.id} is now ${a.status}: ${a.doctor_id}, ${a.date} at ${a.start}`
}

// The backend sends one flat list of events. A caller event starts a new turn.
function groupByTurn(transcript) {
  const turns = []
  for (const event of transcript) {
    if (event.role === 'caller') turns.push([])
    turns[turns.length - 1]?.push(event)
  }
  return turns
}

function Event({ event }) {
  if (event.role === 'tool') {
    return (
      <div className="event">
        <div className="eyebrow event-role">Tool</div>
        <div className={'tool-step' + (event.result.ok ? '' : ' failed')}>
          <div className="strong">{TOOL_TITLES[event.name]}</div>
          <div className="mono tool-call">{rawCall(event)}</div>
          <div className="tool-result">→ {resultText(event)}</div>
        </div>
      </div>
    )
  }
  return (
    <div className="event">
      <div className="eyebrow event-role">{event.role}</div>
      <div className={'bubble ' + event.role}>{event.text}</div>
    </div>
  )
}

// The closing line of the transcript: what happened, in one plain sentence.
function ResultBanner({ result }) {
  const state = STATES[result.terminal_state]
  const reason = REASONS[result.escalation_reason]
  return (
    <div className="event">
      <div className="event-role" />
      <div className={'banner ' + state.tone}>
        {state.title}
        {reason ? ` — ${reason.meaning}` : ''}. {state.meaning}
        {result.appointment_id ? ` (${result.appointment_id}, patient ${result.patient_id})` : ''}
      </div>
    </div>
  )
}

export default function Transcript({ transcript, result }) {
  return (
    <section className="card">
      <h2>Transcript and tool calls</h2>
      <div className="legend">
        <span><i className="swatch caller" /> Caller said</span>
        <span><i className="swatch tool" /> Tool call (a fact from the clinic data)</span>
        <span><i className="swatch agent" /> Agent replied</span>
      </div>
      {groupByTurn(transcript).map((events, index) => (
        <div className="turn" key={index}>
          <div className="turn-title">Turn {index + 1}</div>
          {events.map((event, i) => (
            <Event event={event} key={i} />
          ))}
        </div>
      ))}
      <ResultBanner result={result} />
    </section>
  )
}
