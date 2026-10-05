const ITEMS = [
  { screen: 'queue', label: 'Handoff Queue' },
  { screen: 'conversation', label: 'Conversation Detail' },
]

export default function Sidebar({ screen, onNavigate }) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-logo" title="Sunrise Clinic">S</div>
      {ITEMS.map((item) => (
        <button
          key={item.screen}
          className={'sidebar-item' + (screen === item.screen ? ' active' : '')}
          title={item.label}
          aria-label={item.label}
          aria-current={screen === item.screen ? 'page' : undefined}
          onClick={() => onNavigate(item.screen)}
        >
          <span className="sidebar-dot" />
        </button>
      ))}
    </nav>
  )
}
