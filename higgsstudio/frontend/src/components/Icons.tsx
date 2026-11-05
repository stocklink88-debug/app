interface P { className?: string }
const base = 'w-5 h-5'

const Svg = ({ children, className }: P & { children: React.ReactNode }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" className={className || base}>
    {children}
  </svg>
)

export const IconSpark = (p: P) => <Svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" /></Svg>
export const IconVideo = (p: P) => <Svg {...p}><rect x="2" y="6" width="13" height="12" rx="2" /><path d="M15 10.5l6-3.5v10l-6-3.5z" /></Svg>
export const IconImage = (p: P) => <Svg {...p}><rect x="3" y="3" width="18" height="18" rx="2.5" /><circle cx="8.5" cy="8.5" r="1.6" /><path d="M21 15l-5-5-6.5 7" /></Svg>
export const IconMic = (p: P) => <Svg {...p}><rect x="9" y="2.5" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3.5" /></Svg>
export const IconWave = (p: P) => <Svg {...p}><path d="M3 12h2l2-6 3 14 3-11 2.5 6H21" /></Svg>
export const IconWand = (p: P) => <Svg {...p}><path d="M5 19L17 7M14.5 4.5l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM6 9l.7 1.4L8 11l-1.3.6L6 13l-.7-1.4L4 11l1.3-.6z" /></Svg>
export const IconLayers = (p: P) => <Svg {...p}><path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5" /></Svg>
export const IconFolder = (p: P) => <Svg {...p}><path d="M3 7a2 2 0 012-2h4l2 2.5h8a2 2 0 012 2V17a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></Svg>
export const IconUser = (p: P) => <Svg {...p}><circle cx="12" cy="8" r="4" /><path d="M4.5 20a7.5 7.5 0 0115 0" /></Svg>
export const IconMegaphone = (p: P) => <Svg {...p}><path d="M3 11v2a1 1 0 001 1h2l9 5V5l-9 5H4a1 1 0 00-1 1zM18 9a4 4 0 010 6" /></Svg>
export const IconTool = (p: P) => <Svg {...p}><path d="M14.5 6a4 4 0 105 5l-3-.5-1.5-1.5zM13.5 10.5L4 20l1.5 1.5L15 12" /></Svg>
export const IconGrid = (p: P) => <Svg {...p}><rect x="3" y="3" width="7.5" height="7.5" rx="1.6" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6" /></Svg>
export const IconCompass = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5l-2 5-5 2 2-5z" /></Svg>
export const IconCoins = (p: P) => <Svg {...p}><ellipse cx="12" cy="6.5" rx="7.5" ry="3.5" /><path d="M4.5 6.5v5c0 1.9 3.4 3.5 7.5 3.5s7.5-1.6 7.5-3.5v-5M4.5 11.5v5c0 1.9 3.4 3.5 7.5 3.5s7.5-1.6 7.5-3.5v-5" /></Svg>
export const IconCog = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="3.2" /><path d="M19.4 14a1.6 1.6 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.6 1.6 0 00-2.7 1.1v.2a2 2 0 11-4 0v-.1a1.6 1.6 0 00-2.8-1.1l-.1.1a2 2 0 11-2.8-2.8l.1-.1A1.6 1.6 0 004 14H3.8a2 2 0 110-4h.1A1.6 1.6 0 005 7.3l-.1-.1a2 2 0 112.8-2.8l.1.1A1.6 1.6 0 0010.5 4V3.8a2 2 0 114 0v.1a1.6 1.6 0 002.7 1.1l.1-.1a2 2 0 112.8 2.8l-.1.1a1.6 1.6 0 00-.3 1.8v.1a1.6 1.6 0 001.5 1h.2a2 2 0 110 4h-.1a1.6 1.6 0 00-1.4 1z" /></Svg>
export const IconPlay = (p: P) => <Svg {...p}><path d="M7 4.5l12 7.5-12 7.5z" /></Svg>
export const IconDownload = (p: P) => <Svg {...p}><path d="M12 3v12M7.5 11L12 15.5 16.5 11M4 20h16" /></Svg>
export const IconHeart = (p: P) => <Svg {...p}><path d="M12 20s-7.5-4.6-7.5-9.5A4.2 4.2 0 0112 7.8a4.2 4.2 0 017.5 2.7C19.5 15.4 12 20 12 20z" /></Svg>
export const IconClose = (p: P) => <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>
export const IconPlus = (p: P) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>
export const IconSearch = (p: P) => <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></Svg>
export const IconCheck = (p: P) => <Svg {...p}><path d="M5 13l4.5 4.5L19 7" /></Svg>
export const IconTrash = (p: P) => <Svg {...p}><path d="M4 7h16M9.5 7V5h5v2M6 7l1 13h10l1-13" /></Svg>
export const IconRefresh = (p: P) => <Svg {...p}><path d="M20 11a8 8 0 10-2.3 6.3M20 5.5V11h-5.5" /></Svg>
export const IconUpload = (p: P) => <Svg {...p}><path d="M12 16V4M7.5 8.5L12 4l4.5 4.5M4 20h16" /></Svg>
export const IconFilm = (p: P) => <Svg {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" /></Svg>
export const IconBolt = (p: P) => <Svg {...p}><path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z" /></Svg>
export const IconChevron = (p: P) => <Svg {...p}><path d="M9 6l6 6-6 6" /></Svg>
export const IconMenu = (p: P) => <Svg {...p}><path d="M4 7h16M4 12h16M4 17h16" /></Svg>
export const IconStar = (p: P) => <Svg {...p}><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.7l5.9-.9z" /></Svg>
export const IconCube = (p: P) => <Svg {...p}><path d="M12 2.8l8 4.4v9.6l-8 4.4-8-4.4V7.2zM4 7.2l8 4.4 8-4.4M12 11.6V21" /></Svg>
export const IconScissors = (p: P) => <Svg {...p}><circle cx="6" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><path d="M8 7.5L20 18M8 16.5L20 6" /></Svg>
