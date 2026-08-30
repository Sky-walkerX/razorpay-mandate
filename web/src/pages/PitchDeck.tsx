import { useEffect, useRef } from 'react';

export default function PitchDeck() {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    // Focus the iframe on mount so keyboard navigation works immediately
    const timer = setTimeout(() => {
      iframeRef.current?.focus();
    }, 100);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp', ' ', 'PageDown', 'PageUp', 'Home', 'End', 'f', 'F'].includes(e.key)) {
        try {
          const doc = iframeRef.current?.contentDocument;
          if (doc) {
            doc.dispatchEvent(new KeyboardEvent('keydown', {
              key: e.key,
              code: e.code,
              bubbles: true,
              cancelable: true,
            }));
          }
        } catch {
          // Cross-origin fallback (not needed for same-origin /deck.html)
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  return (
    <div className="fixed inset-0 w-screen h-screen overflow-hidden bg-[#e8e8e5] z-[9999]">
      <iframe
        ref={iframeRef}
        src="/deck.html"
        title="Mandate — Pitch Deck"
        className="w-full h-full border-none block"
        allow="fullscreen"
      />
    </div>
  );
}
