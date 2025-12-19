interface LogoProps {
  className?: string;
}

export function Logo({ className = "" }: LogoProps) {
  return (
    <svg 
      width="40" 
      height="34" 
      viewBox="0 0 100 85" 
      xmlns="http://www.w3.org/2000/svg" 
      aria-label="The Planner's Assistant Logo" 
      className={className}
    >
      <title>Shorter Map Pin Icon with 8-Point Compass Rose</title>
      <desc>
        A deep navy, flat-style map pin with a proportionally reduced height below the compass rose. 
        Features smooth curves and an obtuse point. Contains a detailed golden yellow 8-point compass 
        rose with significantly shorter, wider-based intercardinal points.
      </desc>
      <path 
        id="pin-background" 
        d="M 50 80 C 35 70, 15 55, 15 35 A 35 35 0 1 1 85 35 C 85 55, 65 70, 50 80 Z" 
        fill="var(--color-ink)" 
        stroke="none"
      />
      <g id="compass-rose" transform="translate(0, -15)">
        <path d="M 37.3 37.3 A 18 18 0 0 1 62.7 37.3" stroke="var(--color-brand)" strokeWidth="4" fill="none" />
        <path d="M 62.7 37.3 A 18 18 0 0 1 62.7 62.7" stroke="var(--color-brand)" strokeWidth="4" fill="none" />
        <path d="M 62.7 62.7 A 18 18 0 0 1 37.3 62.7" stroke="var(--color-brand)" strokeWidth="4" fill="none" />
        <path d="M 37.3 62.7 A 18 18 0 0 1 37.3 37.3" stroke="var(--color-brand)" strokeWidth="4" fill="none" />
        <polygon points="50,22 53,50 47,50" fill="var(--color-brand)" />
        <polygon points="50,78 53,50 47,50" fill="var(--color-brand)" />
        <polygon points="76,50 50,52.5 50,47.5" fill="var(--color-brand)" />
        <polygon points="24,50 50,52.5 50,47.5" fill="var(--color-brand)" />
        <polygon points="56.4,43.6 54,50 50,46" fill="var(--color-brand)" />
        <polygon points="56.4,56.4 50,54 54,50" fill="var(--color-brand)" />
        <polygon points="43.6,56.4 46,50 50,54" fill="var(--color-brand)" />
        <polygon points="43.6,43.6 50,46 46,50" fill="var(--color-brand)" />
        <circle cx="50" cy="50" r="3" fill="var(--color-ink)" />
      </g>
    </svg>
  );
}
