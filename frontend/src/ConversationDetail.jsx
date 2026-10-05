import { useEffect, useState } from 'react'
import { getConversation, getConversations, runAgent } from './api.js'
import { REASONS, STATES } from './labels.js'
import Transcript from './Transcript.jsx'
import Outcome from './Outcome.jsx'
import NewCall from './NewCall.jsx'

export default function ConversationDetail({ conversationId, onSelect }) {
  const [list, setList] = useState([])
  const [record, setRecord] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showNewCall, setShowNewCall] = useState(false)

  // Load the list of calls; open the first one if none is chosen yet.
  useEffect(() => {
    getConversations()
      .then((conversations) => {
        setList(conversations)
        if (!conversationId && conversations.length) onSelect(conversations[0].conversation_id)
      })
      .catch((e) => setError(e.message))
  }, [conversationId, onSelect])

  // Load the chosen call.
  useEffect(() => {
    if (!conversationId) return
    getConversation(conversationId)
      .then(setRecord)
      .catch((e) => setError(e.message))
  }, [conversationId])

  // Runs the same call three times, the way the grader does, then shows it.
  async function runThreeTimes(id, today, turns) {
    setBusy(true)
    setError('')
    try {
      for (let i = 0; i < 3; i++) await runAgent(id, today, turns)
      setRecord(await getConversation(id))
      setList(await getConversations())
      onSelect(id)
      setShowNewCall(false)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
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
        {result && (
          <span className={'badge ' + STATES[result.terminal_state].tone}>
            {result.terminal_state.toUpperCase()}
            {reason ? ` — ${reason.label}` : ''}
          </span>
        )}
      </header>

      <div className="toolbar">
        <label>
          <span className="muted">Showing call</span>
          <select value={conversationId || ''} onChange={(e) => onSelect(e.target.value)}>
            {list.length === 0 && <option value="">No calls yet</option>}
            {list.map((c) => (
              <option key={c.conversation_id} value={c.conversation_id}>
                {c.conversation_id} — {c.terminal_state}
              </option>
            ))}
          </select>
        </label>
        <div className="toolbar-buttons">
          {record && (
            <button
              className="button"
              disabled={busy}
              onClick={() => runThreeTimes(record.conversation_id, record.today, record.turns)}
            >
              {busy ? 'Running…' : 'Run again 3 times'}
            </button>
          )}
          <button className="button primary" onClick={() => setShowNewCall(!showNewCall)}>
            {showNewCall ? 'Close' : '+ New call'}
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {(showNewCall || !record) && (
        <NewCall busy={busy} onRun={(today, turns) => runThreeTimes(`ui_${Date.now()}`, today, turns)} />
      )}

      {record && (
        <>
          <div className="detail">
            <Transcript transcript={record.transcript} result={result} />
            <Outcome record={record} />
          </div>
        </>
      )}
    </>
  )
}
