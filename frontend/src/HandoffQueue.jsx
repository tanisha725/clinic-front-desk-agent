import { useEffect, useState } from 'react'
import { getQueue, getSamples, resolveHandoff, runAgent } from './api.js'
import { REASONS } from './labels.js'

// What the caller actually said is shown in quotes; a summary written by the agent is not.
const QUOTED = ['clinical_urgent', 'medical_advice']

function Counter({ label, value, note, noteTone, alert }) {
  return (
    <div className={'card counter' + (alert ? ' alert' : '')}>
      <div className="eyebrow">{label}</div>
      <div className="counter-value">{value}</div>
      <div className={'counter-note ' + (noteTone || '')}>{note}</div>
    </div>
  )
}

export default function HandoffQueue({ onOpen }) {
  const [queue, setQueue] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    getQueue().then(setQueue).catch((e) => setError(e.message))
  }, [])

  async function resolve(id) {
    try {
      setQueue(await resolveHandoff(id))
    } catch (e) {
      setError(e.message)
    }
  }

  // Replays the example and adversarial scripts so the queue has something in it.
  async function replaySamples() {
    try {
      const samples = await getSamples()
      for (const [index, sample] of samples.entries()) {
        setBusy(`Running ${index + 1} of ${samples.length}…`)
        await runAgent(sample.id, sample.today, sample.turns)
      }
      setQueue(await getQueue())
    } catch (e) {
      setError(e.message)
    }
    setBusy('')
  }

  if (error) return <p className="error">Could not reach the backend: {error}</p>
  if (!queue) return <p className="muted">Loading…</p>

  const percent = queue.conversations
    ? Math.round((queue.completed_by_agent / queue.conversations) * 100) + '%'
    : '—'

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Handoff Queue</h1>
          <p className="muted">Sunrise Clinic, Dehradun — conversations the agent escalated</p>
        </div>
        <div className="header-actions">
          <button className="button" onClick={replaySamples} disabled={!!busy}>
            {busy || 'Replay sample calls'}
          </button>
          <span className="badge blue">{queue.open} OPEN</span>
        </div>
      </header>

      <section className="counters">
        <Counter label="Conversations" value={queue.conversations} note="this session" />
        <Counter label="Completed by agent" value={queue.completed_by_agent} note={percent} />
        <Counter label="Escalated" value={queue.escalated} note={`${queue.open} still open`} noteTone="blue" />
        <Counter
          label="Urgent"
          value={queue.urgent_unresolved}
          note="clinical, unresolved"
          noteTone="red"
          alert={queue.urgent_unresolved > 0}
        />
      </section>

      <section className="card">
        <h2>Open handoffs</h2>
        {queue.handoffs.length === 0 ? (
          <div className="empty">
            <p className="strong">Nothing is waiting for a human.</p>
            <p className="muted">Replay the sample calls to see how the agent handles them.</p>
            <button className="button primary" onClick={replaySamples} disabled={!!busy}>
              {busy || 'Replay sample calls'}
            </button>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Conversation</th>
                <th>Caller said</th>
                <th>Reason</th>
                <th>Time</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {queue.handoffs.map((handoff, index) => {
                const reason = REASONS[handoff.reason]
                return (
                  <tr key={handoff.conversation_id} className={reason.tone === 'red' ? 'urgent' : ''}>
                    <td>
                      <button className="link mono" onClick={() => onOpen(handoff.conversation_id)}>
                        {handoff.conversation_id}
                      </button>
                    </td>
                    <td className="strong">
                      {QUOTED.includes(handoff.reason) ? `“${handoff.caller_said}”` : handoff.caller_said}
                    </td>
                    <td>
                      <span className={'badge ' + reason.tone}>{reason.label}</span>
                    </td>
                    <td className="muted">{handoff.time}</td>
                    <td className="right">
                      <button
                        className={'button' + (index === 0 ? ' primary' : '')}
                        onClick={() => resolve(handoff.conversation_id)}
                      >
                        Resolve
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}
