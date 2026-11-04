interface Props {
  score: number
  size?: number
  label?: string
}

/** Anillo de progreso con el potencial viral. */
export default function ScoreRing({ score, size = 54, label }: Props) {
  const clamped = Math.max(0, Math.min(100, score))
  const stroke = Math.max(3, size * 0.09)
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - clamped / 100)

  // Verde fuerte, ámbar medio, coral flojo.
  const color = clamped >= 75 ? '#3DDC97' : clamped >= 55 ? '#FFD24A' : '#FF6B6B'

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color}
          strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="font-bold" style={{ fontSize: size * 0.3, color }}>{Math.round(clamped)}</span>
        {label && <span className="text-[8px] text-slate-500 mt-0.5">{label}</span>}
      </div>
    </div>
  )
}
