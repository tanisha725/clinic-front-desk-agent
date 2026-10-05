// Small inline icons, so the app needs no icon library.
const ICONS = {
  queue: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 13h4l1.5 3h5L16 13h4" />
      <path d="M5.5 5h13L20 13v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-5z" />
    </svg>
  ),
  conversation: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" />
      <path d="M8 9.5h8M8 12.5h5" />
    </svg>
  ),
}

const ITEMS = [
  { screen: 'queue', label: 'Handoff Queue', short: 'Queue' },
  { screen: 'conversation', label: 'Conversation Detail', short: 'Calls' },
]

export default function Sidebar({ screen, onNavigate }) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-logo" title="Sunrise Clinic">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.6"
          strokeLinecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </div>
      {ITEMS.map((item) => (
        <button
          key={item.screen}
          className={'sidebar-item' + (screen === item.screen ? ' active' : '')}
          title={item.label}
          aria-label={item.label}
          aria-current={screen === item.screen ? 'page' : undefined}
          onClick={() => onNavigate(item.screen)}
        >
          {ICONS[item.screen]}
          <span>{item.short}</span>
        </button>
      ))}
    </nav>
  )
}
