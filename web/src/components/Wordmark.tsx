export default function Wordmark({ size = 19 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="0.75" y="0.75" width="18.5" height="18.5" rx="4.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.5 13.5V6.5l4.5 4 4.5-4v7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" />
    </svg>
  );
}
