import { useState } from 'react'
import Sidebar from './Sidebar.jsx'
import HandoffQueue from './HandoffQueue.jsx'
import ConversationDetail from './ConversationDetail.jsx'

// Two screens and one shared sidebar. `screen` decides which one is showing.
export default function App() {
  // A link like /?conversation=cv_0011 opens that conversation directly.
  const linked = new URLSearchParams(window.location.search).get('conversation')
  const [screen, setScreen] = useState(linked ? 'conversation' : 'queue')
  const [conversationId, setConversationId] = useState(linked)

  function openConversation(id) {
    setConversationId(id)
    setScreen('conversation')
  }

  return (
    <div className="layout">
      <Sidebar screen={screen} onNavigate={setScreen} />
      <main className="page">
        {screen === 'queue' ? (
          <HandoffQueue onOpen={openConversation} />
        ) : (
          <ConversationDetail conversationId={conversationId} onSelect={setConversationId} />
        )}
      </main>
    </div>
  )
}
