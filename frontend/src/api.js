// Every call the UI makes to the backend lives here.
// VITE_API_URL is only needed when the frontend is hosted separately from the API.
const BASE = import.meta.env.VITE_API_URL || ''

async function request(path, options) {
  const response = await fetch(BASE + path, options)
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`)
  return body
}

const post = (path, body) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

export const getQueue = () => request('/api/handoffs')
export const resolveHandoff = (id) => post(`/api/handoffs/${id}/resolve`)
export const getConversations = () => request('/api/conversations')
export const getConversation = (id) => request(`/api/conversations/${id}`)
export const getSamples = () => request('/api/samples')
export const runAgent = (conversation_id, today, turns) =>
  post('/agent/run', { conversation_id, today, turns })
