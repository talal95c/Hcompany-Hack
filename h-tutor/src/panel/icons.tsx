const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const IconCursor = () => (
  <svg {...base} width={14} height={14}>
    <path d="M4 3l7 17 2.5-7.5L21 10z" fill="currentColor" stroke="none" />
  </svg>
);
export const IconCheck = () => (
  <svg {...base} width={14} height={14} strokeWidth={3}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </svg>
);
export const IconClose = () => (
  <svg {...base}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);
export const IconSpark = () => (
  <svg {...base} width={15} height={15}>
    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
  </svg>
);
export const IconVolume = () => (
  <svg {...base}>
    <path d="M11 5L6 9H3v6h3l5 4z" />
    <path d="M15.5 8.5a5 5 0 010 7M18.5 5.5a9 9 0 010 13" />
  </svg>
);
export const IconVolumeOff = () => (
  <svg {...base}>
    <path d="M11 5L6 9H3v6h3l5 4z" />
    <path d="M22 9l-6 6M16 9l6 6" />
  </svg>
);
export const IconReplay = () => (
  <svg {...base} width={15} height={15}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
  </svg>
);
export const IconSkip = () => (
  <svg {...base} width={15} height={15}>
    <path d="M5 12h13M13 6l6 6-6 6" />
  </svg>
);
export const IconEnter = () => (
  <svg {...base} width={14} height={14}>
    <path d="M20 5v7a3 3 0 0 1-3 3H5M9 11l-4 4 4 4" />
  </svg>
);
export const IconMic = () => (
  <svg {...base} width={15} height={15}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
export const IconGrid = () => (
  <svg {...base} width={15} height={15}>
    <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" />
  </svg>
);
